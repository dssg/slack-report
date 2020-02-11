#!/usr/bin/env python3
import argparse
import enum
import os

import argcmdr


class StrEnum(str, enum.Enum):

    def __bool__(self):
        return bool(self.value)

    def __str__(self):
        return str(self.value)


class EnvEnum(StrEnum):

    __env_default__ = ''

    def __new__(cls, key):
        value = os.getenv(key, cls.__env_default__)
        obj = str.__new__(cls, value)
        obj.envname = key
        obj._value_ = value
        return obj


class EnvDefaultEnum(EnvEnum):

    def add_help_text(self, help_text):
        display = str(self) if self else 'none'
        default_text = f"(default populated from {self.envname}: {display})"
        return f"{help_text} {default_text}" if help_text else default_text


class EnvDefaultAction(argparse._StoreAction):

    def __init__(self,
                 option_strings,
                 dest,
                 env_default,
                 nargs=None,
                 const=None,
                 type=None,
                 choices=None,
                 required=False,
                 help=None,
                 metavar=None):

        if required and env_default:
            required = False

        super().__init__(
            option_strings,
            dest,
            nargs=nargs,
            const=const,
            default=env_default,
            type=type,
            choices=choices,
            required=required,
            help=env_default.add_help_text(help),
            metavar=metavar,
        )


class Report(argcmdr.Local):
    # TODO: docstring

    # TODO: note oauth scope requirements for two requests: channels.read, etc. and files:write

    class EnvDefault(EnvDefaultEnum):

        api_token = 'SLACK_API_TOKEN'
        channels_url = 'SLACK_CHANNELS_URL'
        upload_url = 'SLACK_UPLOAD_URL'

        # webhook can only post simple messages not file attachments
        # webhook_url = 'SLACK_WEBHOOK'

    channels_url = (EnvDefault.channels_url or
                    'https://slack.com/api/conversations.list')
    upload_url = (EnvDefault.upload_url or
                  'https://slack.com/api/files.upload')

    def __init__(self, parser):
        parser.add_argument(
            '--token',
            action=EnvDefaultAction,
            env_default=self.EnvDefault.api_token,
            help="Slack API token with which to post results",
            required=True,
        )
        parser.add_argument(
            '-c', '--channel',
            action='append',
            dest='channel_names',
            help="channel(s) with which to share results (name)",
        )
        parser.add_argument(
            '-i', '--channel-id',
            action='append',
            dest='channel_ids',
            help="channel(s) with which to share results (id)",
        )
        parser.add_argument(
            '-t', '--title',
            help="title for slack report summary",
        )

        # parser.add_argument(
        #     '-w', '--webhook',
        #     action=EnvDefaultAction,
        #     env_default=self.EnvDefault.webhook_url,
        #     help='Slack webhook URL to which to post results',
        #     metavar='URL',
        #     required=True,
        # )

        parser.add_argument(
            'command',
            help="command to execute",
        )
        parser.add_argument(
            'arguments',
            nargs=argparse.REMAINDER,
            help=argparse.SUPPRESS,
        )

    def report(self, retcode, stdout, stderr):
        channel_ids = self.args.channel_ids

        if self.args.channel_names:
            response = requests.get(self.channels_url, params={
                'token': self.args.token,
                'types': 'private_channel,public_channel',
            })
            data = response.json()
            if not data['ok']:
                return (False, data)

            channel_ids += [
                result['id'] for result in data['channels']
                if result['name'] in self.args.channel_names
            ]

        full_command = self.args.command
        if self.args.arguments:
            full_command += ' ' + ' '.join(self.args.arguments)

        output_type = 'stderr' if retcode else 'stdout'

        comment = (f'the following command returned code `{retcode}` '
                   f'with the attached {output_type}\n\n```{full_command}```')

        if self.args.title:
            comment = f'*{self.args.title}*\n\n{comment}'

        response = requests.post(self.upload_url, data={
            'token': self.args.token,
            'channels': ','.join(channel_ids),
            'initial_comment': comment,
            'title': f'execution output ({output_type})',
            'content': stderr if retcode else stdout,
            'filetype': 'text',
        })
        data = response.json()
        return (data['ok'], data)

    def prepare(self, args):
        (retcode, stdout, stderr) = yield self.local[args.command][args.arguments]

        try:
            (report_ok, report_data) = self.report(retcode, stdout, stderr)
        except Exception as exc:
            if retcode:
                print('slack reporting exception:', exc)
            else:
                raise
        else:
            if not report_ok:
                print('slack reporting error:', report_data)

                retcode = retcode or 1

        raise SystemExit(retcode)

    # disable plumbum exit code exceptions
    prepare.retcode = None


def main():
    argcmdr.main(Report)


if __name__ == '__main__':
    main()
