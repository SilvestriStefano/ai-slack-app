import os

from typing import Union
from pathlib import Path

from flask import Flask
from slack_sdk.web import WebClient
from slackeventsapi import SlackEventAdapter
from dotenv import load_dotenv
import re
import logging
import openai

# create a console logger
logger = logging.getLogger('chatLog')
logger.setLevel(logging.DEBUG) 
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)-8s : %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# constants
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

# Authenticate OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.organization = os.getenv("OPENAI_ORGANIZATION")

# Helping classes for the AI bot
class Message:
  """
  A basic class to create a message as a dict for chat
  """ 
  def __init__(self, role:str, content:str, name:str = None)->None:
    self.role = role
    self.content = content
    self.name = name
    
  def message_for_ai(self)->dict:
    if self.name is not None:
      return {"role": self.role, "name": self.name, "content": self.content}
    else:
      return {"role": self.role, "content": self.content}

class Chat:
  """
  The Chat class is used to preserve the conversation between the user and the bot and to send new messages to it.
  """
  def __init__(self)->None:
    self.conversation_history = []
    
  def _get_assistant_response(self, prompt:list)->Union[Message,str]:
    try:
      completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=prompt
      )
    except openai.error.APIError as e:
      # Handle API error here, e.g. retry or log
      err_msg = f"OpenAI API returned an API Error: {e}"
      logger.error(err_msg)
      return err_msg
    except openai.error.AuthenticationError as e:
      # Handle Authentication error here, e.g. invalid API key
      err_msg = f"OpenAI API returned an Authentication Error: {e}"
      logger.error(err_msg)
      return err_msg
    except openai.error.APIConnectionError as e:
      # Handle connection error here
      err_msg = f"Failed to connect to OpenAI API: {e}"
      logger.error(err_msg)
      return err_msg
    except openai.error.InvalidRequestError as e:
      # Handle connection error here
      err_msg = f"Invalid Request Error: {e}"
      logger.error(err_msg)
      return err_msg
    except openai.error.RateLimitError as e:
      # Handle rate limit error
      err_msg = f"OpenAI API request exceeded rate limit: {e}"
      logger.error(err_msg)
      return err_msg
    except openai.error.ServiceUnavailableError as e:
      # Handle Service Unavailable error
      err_msg = f"Service Unavailable: {e}"
      logger.error(err_msg)
    except openai.error.Timeout as e:
      # Handle request timeout
      err_msg = f"Request timed out: {e}"
      logger.error(err_msg)
    except Exception as e:
      # Handle all other exceptions
      err_msg = f"An exception has occured: {e}"
      logger.error(err_msg)
      return err_msg
    else:
      response_message = Message(
        completion['choices'][0]['message']['role'],
        completion['choices'][0]['message']['content']
      )
      return response_message

  def ask_assistant(self, next_user_prompt:Union[list,dict])->Union[Message,str]:
    if type(next_user_prompt)==dict:
      self.conversation_history.append(next_user_prompt)
    else:
      [self.conversation_history.append(x) for x in next_user_prompt]
    assistant_response = self._get_assistant_response(self.conversation_history)
    if type(assistant_response)==Message:
      self.conversation_history.append(assistant_response.message_for_ai())
    return assistant_response
 
  def _del_conversation(self)->None:
    self.conversation_history = []


SYSTEM_PROMPTS = [
  Message('system',"You are AssistantAI, a seasoned full-stack developer with expertise in Django, React, Flutter, Java Spring framework, and SAS software.You have a strong background in software engineering principles and have extensive experience in managing complex software projects in many programming languages like Python and Javascript. You are well-versed in Agile methodologies and have worked on projects in different domains, including e-commerce, education, healthcare, and finance. As an SEO advisor, you have helped many businesses improve their online visibility and conversion rates through effective search engine optimization strategies. You have a deep understanding of keyword research, on-page optimization, backlink analysis, and content marketing. Your proficiency in database management and design allows you to design efficient databases that optimize performance and scalability. You are highly proficient in SQL and have experience in working with different databases like MySQL, PostgreSQL, Oracle, and MongoDB."),
  Message('system',"For what does SQL stand?", "example_user"),
  Message('system',"SQL stands for Structured Query Language.", "example_assistant")
]
SYSTEM_MSGS = [prompt.message_for_ai() for prompt in SYSTEM_PROMPTS]

history = {} # conversation histories of the users history[userId] = Chat

# Initialize app
app = Flask(__name__)

# Set the callback to validate the bot to be an authorized user
# Bind the Events API route to the existing Flask app by passing the server instance as the last param, or with \`server=app\`.
slack_event_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, endpoint='/slack/events', server=app)

client = WebClient(token=SLACK_BOT_TOKEN)

# Get the bot id
BOT_ID = client.api_call("auth.test")["user_id"] 

@slack_event_adapter.on("app_mention") #  subscribe to only the message events that mention your app or bot
def on_slack_message(event_data):
  event = event_data["event"] # get the event
  channel = event["channel"] # get the channel id
  user = event["user"] # get the user id
  text = event["text"] # get the body of the message
  ts = event["ts"] # get the individual id of the message so we can respond to it in a thread
  
  if BOT_ID in text: #is the bot being addressed?
    try:
      user_assistant = history[user] 
    except KeyError: # the user has never messaged the bot
      history[user] = Chat() # initialize the chat
      user_assistant = history[user]
      user_assistant.ask_assistant(SYSTEM_MSGS) # provide the bot with the system prompts
    finally:
      prompt = "".join(re.split(r"(?:<@[A-Z0-9]*>)", text)) # remove the bot mention (<@BOT_ID>) from the message
      user_input = Message("user", prompt)
      response = user_assistant.ask_assistant(user_input.message_for_ai()) # prompt the bot
      answer = response if type(response)==str else response.content 
      client.chat_postMessage(channel=channel, thread_ts=ts, text=answer)
    

    
app.run(host="0.0.0.0", port=5000)