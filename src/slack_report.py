#!/usr/bin/env python3
"""Execute a command and report its results to Slack

Requires a Slack API token with permissions:

* to post result file: ``files:write``
* to look up requested channels by name: ``channels.read``

As an alternative to command flag ``--token``, this token may be
indicated via process environment variable: ``SLACK_API_TOKEN``.

Slack API URLs may be overridden only via environment variables:

* ``SLACK_CHANNELS_URL``
* ``SLACK_UPLOAD_URL``

"""
import argparse
import enum
import os
import sys

import argcmdr
import requests


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
    """execute command and report exit code & outputs to Slack"""

    class EnvDefault(EnvDefaultEnum):

        api_token = 'SLACK_API_TOKEN'
        channels_url = 'SLACK_CHANNELS_URL'
        upload_url = 'SLACK_UPLOAD_URL'
        max_width = 'SLACK_REPORT_WIDTH'

        # webhook can only post simple messages not file attachments
        # webhook_url = 'SLACK_WEBHOOK'

    channels_url = (EnvDefault.channels_url or
                    'https://slack.com/api/conversations.list')
    upload_url = (EnvDefault.upload_url or
                  'https://slack.com/api/files.upload')

    @property
    def max_width(self):
        if self.EnvDefault.max_width.isdigit():
            return int(self.EnvDefault.max_width)

        return 80

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
            metavar='NAME',
        )
        parser.add_argument(
            '-i', '--channel-id',
            action='append',
            dest='channel_ids',
            help="channel(s) with which to share results (id)",
            metavar='ID',
        )
        parser.add_argument(
            '-t', '--title',
            help="title for report summary",
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
            help="command to execute & report on",
        )
        parser.add_argument(
            'arguments',
            metavar='[args...]',
            nargs=argparse.REMAINDER,
            help=argparse.SUPPRESS,
        )

    def report(self, retcode, stdout, stderr):
        channel_ids = self.args.channel_ids or []

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

        comment = (f'the following command returned code `{retcode}`\n\n'
                   f'```{full_command}```\n\n'
                   f'with the attached stdout and stderr')

        if self.args.title:
            comment = f'*{self.args.title}*\n\n{comment}'

        # match content banner widths to output
        output_width = max(len(line) for output in (stdout, stderr)
                           for line in output.splitlines())
        # ...so long as that's nothing insane (beyond max)
        output_width = min(output_width, self.max_width)
        # ...(nor below the banners' minima: " begin stdout ")
        output_width = max(output_width, 16)

        response = requests.post(self.upload_url, data={
            'token': self.args.token,
            'channels': ','.join(channel_ids),
            'initial_comment': comment,
            'title': 'command execution output',
            'content': '\n'.join(
                f' begin {name} '.center(output_width, '=') + '\n' +
                f'\n{output}\n' +
                f' end {name} '.center(output_width, '=') + '\n'
                for (name, output) in (
                    ('stdout', stdout),
                    ('stderr', stderr),
                )
            ),
            'filetype': 'text',
        })
        data = response.json()
        return (data['ok'], data)

    def prepare(self, args, parser):
        try:
            (retcode, stdout, stderr) = yield self.local[args.command][args.arguments]
        except self.local.CommandNotFound:
            print(f'{parser.prog}: error: cannot run {args.command}: not found', file=sys.stderr)
            raise SystemExit(127)

        if stdout is None:
            # dry run
            return

        try:
            (report_ok, report_data) = self.report(retcode, stdout, stderr)
        except Exception as exc:
            if retcode:
                print(f'{parser.prog}: exception:', exc, file=sys.stderr)
            else:
                raise
        else:
            if report_ok:
                permalink = report_data.get('file', {}).get('permalink')
                report_message = f'{parser.prog}: ok'
                if permalink:
                    report_message += f': {permalink}'

                print(report_message, file=sys.stderr)
            else:
                retcode = retcode or 1

                print(f'{parser.prog}: error:', report_data, file=sys.stderr)

        raise SystemExit(retcode)

    # disable plumbum exit code exceptions
    prepare.retcode = None


def main():
    argcmdr.main(Report)


if __name__ == '__main__':
    main()
