# Demo Script Generator Web App

A next.js app with a single page that allows users to point to their company's product website, include files, images and written descriptions and outputs a text file that contains a well-structured, story-telling demo-script. 

This will be rendered as an AI/LLM chat. The LLM can ask the user questions to clarify key things needed for crafting the demo. 

The demo script should follow best practices such as:

- Focus on 3 Key Ideas: the audience can only remember 3 ideas that they emotionally attach to

For each idea, a key visual, illustration or meaningful data point that brings that idea to life. 

The demo should also include story elements - who is the user? How do they benefit from this product being demoed?

The overall structure should be tell-show-tell. 

Outline of script:

- Limbic opening - e.g. Did you know that 40% of customer data is in the data warehouse and not the CRM?
The limibic opening is an attention grabber

Initial tell:
- Tell the audience what they will see. Provide an initial statement around the 3 key ideas.

Show:
- Show the audience each of the key ideas in sequence with the accompanying visuals, illustrations and or data points

Closing tell:
Remind the audience what they saw in a summarizing close.

This is an MVP - just a simple single page web app for now. 

- Keep it simple
- Don't write overly defensive programming
- Avoid things like _isintance checks
- Concise readme files. No emojis
- The LLM provider will be OpenAI - I'll provide an API key later.
- Python backend with FastAPI for the LLM interactions
- Next.js modern frontend for the LLM chat with streaming
- Everything should run in Docker with start and stop scripts for Mac
- No need for any database, user management for now