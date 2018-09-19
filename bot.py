# author: Paul Galatic
# 
# boilerplate code from:
#   fullstackpython.com
#   https://github.com/mattmakai

import os
import re
import pdb
import time
import urllib
import requests
import traceback
import validators
from scipy import misc
from io import BytesIO
from kmeans import kMeans
from mnist import mnist
from slackclient import SlackClient
from download_img import download_img

# instantiate Slack client
slack_client = SlackClient(os.environ.get('APP_BOT_USER_TOKEN'))
# starterbot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None

# constants
RTM_READ_DELAY = 1 # second delay between reading from RTM
HELP_COMMAND = 'help'
KMEANS_COMMAND = 'kmeans'
MNIST_COMMAND = 'mnist'
MENTION_REGEX = '^<@(|[WU].+?)>(.*)'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'}

def check_url(url):
    """
    Returns True if the url returns a response code between 200-300,
    otherwise return False.

    author: Matto Todd
    """

    try:
        response = requests.get(url, headers=HEADERS)
    except ConnectionError:
        return False

    if 200 <= response.status_code <= 200:
        return True

    return False

def parse_bot_commands(slack_events):
    """
    Parses a list of events coming from the Slack RTM API to find bot commands.
    If a bot command is found, this function returns a tuple of command and 
    channel. If its not found, then this function returns None, None.
    """
    for event in slack_events:
        if event['type'] == 'message' and not 'subtype' in event:
            # pdb.set_trace()
            user_id, message = parse_direct_mention(event['text'])
            if user_id == starterbot_id:
                return message, event['channel']
    return None, None

def parse_direct_mention(message_text):
    """
    Finds a direct mention (a mention that is at the beginning) in message text
    and returns the user ID which was mentioned. If there is no direct mention, 
    returns None
    """
    matches = re.search(MENTION_REGEX, message_text)
    # the first group contains the username
    # the second group contains the remaining message
    if matches:
        return (matches.group(1), matches.group(2).strip())
    else:
        return (None, None)

def handle_command(command, channel):
    """
    Executes bot command if the command is known
    """
    # Default response is help text for the user
    default_response = 'Unknown command. Try *{}*.'.format(KMEANS_COMMAND)
    error_response = 'There was an unknown error. Whoops, please edit.'

    try:
        if command.startswith(HELP_COMMAND):
            bot_help(command, channel)

        elif command.startswith(KMEANS_COMMAND):
            bot_kmeans(command, channel)

        elif command.startswith(MNIST_COMMAND):
            bot_mnist(command, channel)

        else:
            respond(default_response, channel)
    except Exception as e:
        with open('elog.txt', 'a') as f:
            f.write(str(e))
            f.write(traceback.format_exc())
            print(traceback.format_exc())
        respond(error_response, channel)

def respond(message, channel):
    slack_client.api_call(
        'chat.postMessage',
        channel=channel,
        text=message
    )

def bot_help(command, channel):
    command_list = command.split(' ')
    
    # default response
    message =   'Available commands:\n' +\
                '\t@ritai help\n' +\
                '\t@ritai mnist [image_url]' +\
                '\t@ritai kmeans [image_url] [k_value]'
    
    # specific responses
    if len(command_list) == 2:
        if command_list[1] == KMEANS_COMMAND:
            message = 'usage: @ritai kmeans [image_url] [k_value]'

    respond(message, channel)

def bot_mnist(command, channel):
    command_list = command.split(' ')
    # make sure all command arguments are present with no extras
    if len(command_list) != 2:
        respond('Usage: @ritai mnist [image_url]', channel)
        return
    
    img_url = command_list[1]

    if img_url.startswith('<'):
        img_url = img_url[1:-2]
    
    # validate url
    if not check_url(img_url):
        respond('Could not validate url.', channel)
        return

    download_img(img_url, 'in.png')

    # perform mnist
    img = misc.imread('in.png', flatten=True)
    prediction = mnist.query(img)

    # report prediction
    respond('I think this is a... %d.' % prediction, channel)

def bot_kmeans(command, channel):
    command_list = command.split(' ')
    # make sure all command arguments are present with no extras
    if len(command_list) != 3:
        respond('Usage: @ritai kmeans [image_url] [k_value]', channel)
        return

    img_url = command_list[1]
    k_value = command_list[2]
  
    if img_url.startswith('<'):
        img_url = img_url[1:-1]

    # validate url and k-value
    if not check_url(img_url):
        respond('Could not validate url.', channel)
        return
    try:
        k_value = int(k_value)
    except ValueError:
        respond('K value must be an integer')
        return
    if not (0 < k_value < 11):
        respond('K value must be between 1 and 10 inclusive.', channel)
        return

    # acquire image
    download_img(img_url, 'in.png')

    # perform kMeans
    im = misc.imread('in.png')
    newIm = kMeans(im, k_value)
    misc.imsave('out.png', newIm)

    # post image to channel
    with open('out.png', 'rb') as f:
        slack_client.api_call(
            'files.upload',
            channels=[channel],
            filename='out.png',
            title='output',
            initial_comment=('k: %d' % k_value),
            file=f
        )

if __name__ == '__main__':
    if slack_client.rtm_connect(with_team_state=False):
        print('ritai-bot is connected and running!')
        # Read bot's user ID by calling Web API method `auth.test`
        starterbot_id = slack_client.api_call('auth.test')['user_id']
        while True:
            command, channel = parse_bot_commands(slack_client.rtm_read())
            if command:
                handle_command(command, channel)
            time.sleep(RTM_READ_DELAY)
    else:
        print('Connection failed. Exception traceback printed above.')
