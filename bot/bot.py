# author: Paul Galatic
# 
# boilerplate code from:
#   fullstackpython.com
#   https://github.com/mattmakai

# standard libraries
import os
import re
import sys
import pdb
import time
import requests
import traceback
import abc
import asyncio

# additional libraries
from slackclient import SlackClient

import discord
from discord.ext import commands

# project-specific libraries
from .skill.help import help
from .skill.mnist import mnist
from .skill.kmeans import kmeans
from .skill.stylize import stylize
from .skill.caption import caption
from . import const

TIME_FORMAT = '%H:%M:%S'
ELOG_CHANNEL = 'test_bots'
# A dictionary of string prompts mapping to functions
CATALOGUE = {
    const.HELP_PROMPT: help.SkillHelp(),
    const.KMEANS_PROMPT: kmeans.SkillKmeans(),
    const.MNIST_PROMPT: mnist.SkillMnist(),
    const.STYLIZE_PROMPT: stylize.SkillStylize(),
    const.CAPTION_PROMPT: caption.SkillCaption()
}


class _AbstractBotPort(abc.ABC):
    def __init__(self, bot_token):
        super().__init__()
        self.bot_token = bot_token

    @abc.abstractmethod
    def parse_direct_mention(self):
        raise NotImplementedError

    @abc.abstractmethod
    def launch_bot(self):
        raise NotImplementedError

    @abc.abstractmethod
    def parse_bot_commands(self):
        raise NotImplementedError

    @abc.abstractmethod
    def download_attached_image(self):
        raise NotImplementedError

    @abc.abstractmethod
    def post_error(self, error, client):
        raise NotImplementedError

    def log(self, s):
        '''More informative print debugging'''
        print('[%s]: %s' % (time.strftime(TIME_FORMAT, time.localtime()), str(s)))

    def handle_prompt(self, prompt, info):
        '''
        Executes bot prompt if the prompt is known. The bot runs continuously and
        logs errors to a file.
        '''

        # Help is a special Skill that we use to inform the user as to what the bot
        # can and cannot do
        Help = CATALOGUE[const.HELP_PROMPT]
        Help.set_info(info)

        try:
            # get the first and second words of the sent message (if they exist)
            words = prompt.split(' ')
            firstword = words[0]
            if len(words) > 1:
                secondword = words[1]
            else:
                secondword = None

            # if the first word is asking for clarification, print a message
            if firstword == const.HELP_PROMPT:
                # send clarification about a command
                if secondword and secondword in CATALOGUE.keys():
                    CATALOGUE[secondword].set_info(info)
                    CATALOGUE[secondword].help()
                # send general clarification
                else:
                    Help.help()

            elif prompt.startswith(const.ERROR_PROMPT):
                raise Exception('please edit')

            # if we recognize the command, then execute it
            elif firstword in CATALOGUE.keys():
                CATALOGUE[firstword].set_info(info)
                CATALOGUE[firstword].execute(prompt)

            # otherwise, warn the user that we don't understand
            else:
                Help.execute(prompt)

        except Exception:
            # we don't want the bot to crash because we cannot easily restart it
            # this default response will at least make us aware that there's an
            # error happening, so we can hopefully replicate and fix it on the
            # dev version of the bot
            err = traceback.format_exc()
            if not os.path.isdir(const.LOG_PATH):
                os.makedirs(const.LOG_PATH)
            with open(str(const.LOG_PATH / 'elog.txt'), 'a') as elog:
                elog.write('[%s]: %s\n' % (time.strftime(TIME_FORMAT, time.localtime()), prompt))
                elog.write('[%s]: %s\n' % (time.strftime(TIME_FORMAT, time.localtime()), err))
            self.post_error(err, info[const.INFO_CLIENT])
            self.log(err)
            Help.error()

    @abc.abstractmethod
    def main(self):
        raise NotImplementedError

class DiscordBotPort(_AbstractBotPort):

    def __init__(self, bot_token):
        super().__init__(bot_token=bot_token)
        self.client = discord.Client()
        # "Binds" callback functions to 'on_ready' and 'on_message'
        self.on_ready = self.client.event(self.on_ready)
        self.on_message = self.client.event(self.on_message)

        self.main()

    def get_connection_status(self):
        return self.connection_status

    def parse_direct_mention(self, message_text):
        '''
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention,
        returns None
        '''
        matches = re.search(const.MENTION_REGEX_DISCORD, message_text)
        # the first group contains the username
        # the second group contains the remaining message
        if matches:
            return (matches.group(1), matches.group(2).strip())
        else:
            return (None, None)
    
    def parse_bot_commands(self):
        pass

    def download_attached_image(self, message):
        '''Download an image attached to a message'''
        for attachment in message.attachments:
            response = requests.get(attachment.url, stream=True)

            if not os.path.isdir(const.TEMP_PATH):
                os.makedirs(const.TEMP_PATH)

            with open(const.TEMP_PATH / const.IN_IMG_NAME, 'wb') as image:
                image.write(response.content)

    def post_error(self, error, client):
        '''Posts stack trace to a channel dedicated to bot maintenance'''
        for guild in self.client.guilds:
            for channel in guild.text_channels:
                if channel.name == ELOG_CHANNEL:
                    error = '```\n' + error + '```'
                    asyncio.create_task(channel.send(error))
    
    def log(self, s):
        '''More informative print debugging'''
        super().log("Discord Port | " + s)

    async def on_ready(self):
        '''
        Gets called when bot connects successfully
        '''
        self.connection_status = const.SUCCESSFUL_CONNECTION
        self.bot_ID = str(self.client.user.id) 
        self.log('ritai-bot connected and running!')

    async def on_message(self, message):
        '''
        Gets called whenever a message gets sent in the server
        '''
        ID, content = self.parse_direct_mention(message.content)
        if ID == self.bot_ID:
            if(len(message.attachments) != 0):
                self.download_attached_image(message)

    def launch_bot(self):
        '''
        Starts the discord bot
        @NOTE This method is blocking
        '''
        try:
            self.client.run(self.bot_token)
        except:
            traceback.print_exc()
            self.log('Connection failed. Exception traceback printed above.')
            self.connection_status = const.FAILED_CONNECTION

    def main(self):
        self.launch_bot()


class SlackBotPort(_AbstractBotPort):
    def __init__(self, bot_token):
        super().__init__(bot_token=bot_token)
        self.client, self.bot_name, self.connection_status = self.launch_bot()

    def get_connection_status(self):
        return self.connection_status
    
    def parse_direct_mention(self, message_text):
        '''
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention,
        returns None
        '''
        matches = re.search(const.MENTION_REGEX, message_text)
        # the first group contains the username
        # the second group contains the remaining message
        if matches:
            return (matches.group(1), matches.group(2).strip())
        else:
            return (None, None)


    def parse_bot_commands(self, slack_events, bot_name, bot_token):
        '''
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot prompt is found, this function returns a tuple of prompt and
        channel. If its not found, then this function returns None, None.
        '''
        for event in slack_events:
            if event['type'] == 'message' and not 'subtype' in event:
                user_name, message = self.parse_direct_mention(event['text'])
                if user_name == bot_name:
                    # download a file if it was present in the message
                    if 'files' in event:
                        # file is present
                        f = event['files'][0]
                        self.download_attached_image(f['url_private_download'], bot_token)
                    # reply to the parent thread, not the child thread
                    if 'thread_ts' in event:
                        thread = event['thread_ts']
                    else:
                        thread = event['ts']

                    return message, event['channel'], thread
        return None, None, None

    def download_attached_image(self, img_url, bot_token):
        '''Downloads an image from a url'''
        # sometimes slack packages urls in messages in brackets
        # these will cause an error unless we remove them
        if img_url[0] == '<':
            img_url = img_url[1:-1]

        headers = {'Authorization': 'Bearer %s' % bot_token}
        response = requests.get(img_url, headers=headers)

        if not os.path.isdir(const.TEMP_PATH):
            os.makedirs(const.TEMP_PATH)

        with open(const.TEMP_PATH / const.IN_IMG_NAME, 'wb') as image:
            image.write(response.content)

    def post_error(self, error, client):
        '''Posts stack trace to a channel dedicated to bot maintenance'''
        channels = client.api_call(method='conversations.list', exclude_archived=1)['channels']
        if channels:
            elog_channel = None
            for channel in channels:
                if channel['name'] == ELOG_CHANNEL:
                    elog_channel = channel['id']
                    break
            if not elog_channel:
                self.log('WARNING: No channel in which to log errors!')

            error = '```\n' + error + '```'  # makes it look fancy, I think

            client.api_call(
                'chat.postMessage',
                channel=elog_channel,
                text=error,
            )

    def log(self, s):
        '''More informative print debugging'''
        super().log("Slack Port | " + s)

    def launch_bot(self):
        try:
            # instantiate Slack client
            client = SlackClient(self.bot_token)

            # try to connect to slack
            if client.rtm_connect(with_team_state='False'):
                # Read bot's user ID by calling Web API method `auth.test`
                bot_name = client.api_call('auth.test')['user_id']
                # connection is successful
                self.log('ritai-bot connected and running!')
                self.client = client
            return client, bot_name, const.SUCCESSFUL_CONNECTION
        except:
            traceback.print_exc()
            self.log('Connection failed. Exception traceback printed above.')
            return None, None, const.FAILED_CONNECTION

    def main(self):
        # Checking for mentions
        prompt, channel, thread = self.parse_bot_commands(self.client.rtm_read(), self.bot_name, self.bot_token)
        if prompt:
            self.log(prompt)
            # info is an object that lets the bot keep track of who it's responding to.
            info = {
                const.INFO_CLIENT: self.client,
                const.INFO_CHANNEL: channel,
                const.INFO_THREAD: thread
            }
            self.handle_prompt(prompt, info)

    

def run_bot_ports(run_discord_port=False, run_slack_port=False):
    bot_ports = []

    if run_discord_port:
        discord_bot_token = os.environ.get('DISCORD_BOT_USER_TOKEN')
        discord_bot = DiscordBotPort(discord_bot_token)
        if discord_bot.get_connection_status() == const.SUCCESSFUL_CONNECTION:
            bot_ports.append(discord_bot)
        else:
            discord_bot.log('Could not connect to discord client.')

    if run_slack_port:
        slack_bot_token = os.environ.get('SLACK_BOT_USER_TOKEN')
        slack_bot = SlackBotPort(slack_bot_token)
        if slack_bot.launch_bot() == const.SUCCESSFUL_CONNECTION:
            bot_ports.append(slack_bot)
        else:
            slack_bot.log('Could not connect to slack client.')

    while True:
        for bot_port in bot_ports:
            bot_port.main()
        time.sleep(const.RTM_READ_DELAY / len(bot_ports))


if __name__ == '__main__':
    run_bot_ports()
