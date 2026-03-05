# Create a power detector and warning signal generator

You are to create a power detector that can detect power loss and send a warning sms message when power has been lost for > 60 seconds.

## Who are you

You are an expert software developer well-versed in cloud tech, python, web tech, and IoT. You develop easy-to-read code that is maintainable and easy to test and debug. 

## Assumptions

1. Standalone application
2. Zero cost to execute and deploy
3. Can use cloud if we conform to zero cost
4. The home has IoT devices from Shelly, FEIT, and some others
5. The home has Alexa
6. The wifi is on a UPS, therefore, will stay up for some period of time in the event of power loss.

## First Job
Ask clarifying questions. Add those questions and answers to a Markdown document in this repo for historical purposes. 

## The Plan
Create a plan. Evaluate several methods and create a document that details this plan, your assumptions, your evaluation of choices, and a recommendation. 

Detail where the code will run and how to deploy it.

Create an architecture diagram and an interconnection diagram and add these to the plan document. Render them as images.

## Implementation
Once we agree on the plan, you will implement as much as you can in Python. All python files will conform 100% to template.py. That includes:
- style and structure
- logging and stdout style
- arg parsing
- string delimiters
- line endings in multiline statements
- assume venv and create the requirements.txt