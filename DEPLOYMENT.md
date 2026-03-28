# Deployment: Vercel (Frontend) + Fly.io (Backend)

Deploy the Next.js frontend to Vercel and the FastAPI backend to Fly.io. Both have generous free tiers.

## What you get for free

| Service | Free tier |
|---------|-----------|
| **Vercel** | Unlimited static/serverless deploys, custom domains, automatic HTTPS, global CDN |
| **Fly.io** | 3 shared-cpu-1x VMs, 256 MB RAM each, 3 GB persistent storage, 160 GB outbound transfer |

## Prerequisites

- A GitHub (or GitLab/Bitbucket) account with this repo pushed to it
- [Fly CLI](https://fly.io/docs/flyctl/install/) installed: `brew install flyctl`
- A Vercel account (sign up at https://vercel.com)
- A Fly.io account (sign up at https://fly.io)

---

## Part 1: Deploy the Backend to Fly.io

### 1.1 Authenticate

```bash
fly auth login
```

### 1.2 Create the Fly app

From the repo root:

```bash
cd backend
fly launch --no-deploy
```

When prompted:
- **App name**: pick something like `demo-script-gen-api` (must be globally unique)
- **Region**: choose one close to your users
- **Database**: no
- **Redis**: no

This creates a `fly.toml` file in `backend/`.

### 1.3 Configure fly.toml

Replace the generated `fly.toml` with:

```toml
app = 'demo-script-gen-api'  # your app name from above
primary_region = 'ord'        # your chosen region

[build]
  dockerfile = 'Dockerfile'

[env]
  OPENAI_MODEL = 'gpt-4o'

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = 'stop'
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  memory = '256mb'
  cpu_kind = 'shared'
  cpus = 1
```

### 1.4 Set secrets

```bash
fly secrets set OPENAI_API_KEY=sk-your-actual-key
```

You'll set `FRONTEND_ORIGIN` after deploying the frontend (step 2.3).

### 1.5 Deploy

```bash
fly deploy
```

Once deployed, your backend is live at:

```
https://demo-script-gen-api.fly.dev
```

Verify:

```bash
curl https://demo-script-gen-api.fly.dev/health
```

---

## Part 2: Deploy the Frontend to Vercel

### 2.1 Connect the repo

1. Go to https://vercel.com/new
2. Import your Git repository
3. Set the **Root Directory** to `frontend`
4. Framework Preset will auto-detect **Next.js**

### 2.2 Set environment variables

In the Vercel project settings (**Settings > Environment Variables**), add:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://demo-script-gen-api.fly.dev` |

Replace with your actual Fly.io app URL.

### 2.3 Deploy

Click **Deploy**. Vercel will build and deploy the frontend. Your site will be live at:

```
https://your-project.vercel.app
```

### 2.4 Set the CORS origin on Fly.io

Now that you have the Vercel URL, go back and set the backend's allowed origin:

```bash
cd backend
fly secrets set FRONTEND_ORIGIN=https://your-project.vercel.app
```

This configures the FastAPI CORS middleware to accept requests from your frontend.

---

## Part 3: Custom Domain (Optional)

### Vercel (frontend)

1. Go to **Project Settings > Domains**
2. Add your domain (e.g., `demo.yourdomain.com`)
3. Update your DNS with the records Vercel provides

### Fly.io (backend)

```bash
fly certs create api.yourdomain.com
```

Then add a CNAME record pointing `api.yourdomain.com` to `demo-script-gen-api.fly.dev`.

After adding a custom domain, update the environment variables:

```bash
# On Fly.io -- update allowed origin
fly secrets set FRONTEND_ORIGIN=https://demo.yourdomain.com

# On Vercel -- update API URL in project settings
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

Redeploy the frontend on Vercel after changing environment variables (or trigger a redeploy from the dashboard).

---

## Updating the App

### Frontend

Push to your main branch. Vercel auto-deploys on every push.

### Backend

```bash
cd backend
fly deploy
```

Or set up continuous deployment with `fly deploy` in a GitHub Action.

---

## Troubleshooting

**Frontend can't reach the backend (CORS errors)**
- Verify `FRONTEND_ORIGIN` on Fly.io matches your exact Vercel URL (including `https://`, no trailing slash)
- Verify `NEXT_PUBLIC_API_URL` on Vercel points to your Fly.io app URL
- Redeploy both after changing env vars

**Backend deploy fails**
- Check logs: `fly logs`
- Verify secrets are set: `fly secrets list`
- Ensure the Dockerfile builds locally: `docker build ./backend`

**Backend is slow to respond**
- First request after idle may take a few seconds (machine auto-starts from stopped state)
- Set `min_machines_running = 1` in `fly.toml` to keep it warm (uses more free-tier hours)

**Vercel build fails**
- Check that Root Directory is set to `frontend`
- Check build logs in the Vercel dashboard
- Verify the build works locally: `cd frontend && npm run build`

**ARM compatibility**
- Fly.io runs on x86_64 by default; the `python:3.12-slim` base image works without changes
- No ARM-specific concerns on Vercel (it runs your Next.js build, not Docker)
