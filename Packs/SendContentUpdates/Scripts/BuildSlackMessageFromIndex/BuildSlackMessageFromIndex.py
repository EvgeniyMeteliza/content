import demistomock as demisto  # noqa: F401
from CommonServerPython import *  # noqa: F401
import json
import os
from tempfile import mkdtemp
from zipfile import ZipFile
from datetime import datetime

DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
MP_LINK = "https://xsoar.pan.dev/marketplace"
MP_PACK_LINK = f"{MP_LINK}/details"


class IndexPack:
    def __init__(self, path, pack_id):
        self.pack_index_path = path
        self.id = pack_id
        self._metadata_path = None
        self._metadata = None
        self._name = None
        self._created = None
        self._price = None
        self._is_private_pack = None
        self._support = None
        self._author = None
        self._description = None

    @property
    def name(self):
        if not self._name:
            self._name = self.metadata.get('name')
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def metadata(self):
        if not self._metadata:
            if self.metadata_path:
                self._metadata = load_json(self._metadata_path)
            else:
                self._metadata = {}
        return self._metadata

    @metadata.setter
    def metadata(self, metadata):
        self._metadata = metadata

    @property
    def metadata_path(self):
        if not self._metadata_path:
            metadata_path = os.path.join(self.pack_index_path, 'metadata.json')
            if os.path.exists(metadata_path):
                self._metadata_path = metadata_path
            else:
                demisto.error(f'metadata.json file was not found for pack: {self.id}')
                self._metadata_path = ''
        return self._metadata_path

    @metadata_path.setter
    def metadata_path(self, metadata_path):
        self._metadata_path = metadata_path

    @property
    def created(self):
        if not self._created:
            self._created = self.metadata.get('created')
        return self._created

    @created.setter
    def created(self, created):
        self._created = created

    @property
    def price(self):
        if not self._price:
            self._price = self.metadata.get('price', 0)
        return self._price

    @price.setter
    def price(self, price):
        self._price = price

    @property
    def is_private_pack(self):
        if self._is_private_pack is None:
            self._is_private_pack = True if self._metadata.get('partnerId') else False
        return self._is_private_pack

    @is_private_pack.setter
    def is_private_pack(self, is_private_pack):
        self._is_private_pack = is_private_pack

    @property
    def support(self):
        if self._support is None:
            self._support = self._metadata.get('support', 'xsoar')
        return self._support

    @support.setter
    def support(self, support):
        self._support = support

    @property
    def author(self):
        if not self._author:
            self._author = self._metadata.get('author', 'Cortex XSOAR')
        return self._author

    @author.setter
    def author(self, author):
        self._author = author

    @property
    def description(self):
        if not self._description:
            self._description = self._metadata.get('description')
        return self._description

    @description.setter
    def description(self, description):
        self._description = description

    def is_released_after_last_run(self, last_run):
        demisto.debug(f'{self.id} pack was created at {self.created}')
        created_datetime = datetime.strptime(self.created, DATE_FORMAT)
        last_run_datetime = datetime.strptime(last_run, DATE_FORMAT)
        return created_datetime > last_run_datetime

    def to_context(self):
        return {
            'name': self.name,
            'id': self.id,
            'is_private_pack': self.is_private_pack,
            'price': self.price,
            'support': self.support,
            'author': self.author,
            'description': self.description
        }


def load_json(file_path: str) -> dict:
    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r') as json_file:
                result = json.load(json_file)
        else:
            result = {}
        return result
    except json.decoder.JSONDecodeError:
        return {}


def get_file_data(file_entry_id):
    res = demisto.executeCommand('getFilePath', {'id': file_entry_id})

    if res[0]['Type'] == entryTypes['error']:
        raise Exception(f'Failed getting the file path for entry {file_entry_id}')

    return res[0]['Contents']


def extract_index(args):
    index_entry_id = args['entry_id']
    index_data = get_file_data(index_entry_id)
    download_index_path = index_data['path']

    extract_destination_path = mkdtemp()
    index_folder_path = os.path.join(extract_destination_path, 'index')

    if os.path.exists(download_index_path):
        demisto.info('Found existing index.zip')
        with ZipFile(download_index_path, 'r') as index_zip:
            index_zip.extractall(extract_destination_path)
        demisto.info(f'Extracted index.zip successfully to {index_folder_path}')
    else:
        error_msg = f'File was not found at path {download_index_path}'
        demisto.error(error_msg)
        raise Exception(error_msg)

    if not os.path.exists(index_folder_path):
        error_msg = 'Failed creating index folder with extracted data.'
        demisto.error(error_msg)
        raise Exception(error_msg)

    return index_folder_path


def get_new_packs(args, index_folder_path):
    new_packs = []
    last_msg_time_str = args['last_message_time_str']
    demisto.info(f'last message time was: {last_msg_time_str}')

    for file in os.scandir(index_folder_path):
        if os.path.isdir(file):
            pack = IndexPack(file.path, file.name)
            if pack.is_released_after_last_run(last_msg_time_str):
                new_packs.append(pack.to_context())
                demisto.info(f'{file.name} pack is a new pack')

    return new_packs


def get_divider_block():
    return {
        "type": "divider"
    }


def build_header_block(num_new_packs):
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"We have *{num_new_packs} New Packs* this week!"
        }
    }


def build_pack_section_block(pack_name, pack_id, pack_author, pack_description):
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*<{MP_PACK_LINK}/{pack_id}|{pack_name}>*\nBy: {pack_author}\n\n{pack_description}"
        }
    }


def build_pack_context_block(price, support):
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "FREE" if str(price) == "0" else f"{price} Points"
            },
            {
                "type": "mrkdwn",
                "text": f'{":cortexpeelable: XSOAR" if support == "xsoar" else support.capitalize()} Supported'
            }
        ]
    }


def build_pack_blocks(pack):
    pack_name = pack['name']
    pack_id = pack['id']
    pack_price = pack['price']
    pack_support = pack['support']
    pack_author = pack['author']
    pack_description = pack['description']

    return [
        build_pack_section_block(pack_name, pack_id, pack_author, pack_description),
        build_pack_context_block(pack_price, pack_support)
    ]


def get_bottom_block():
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"See all of Palo Alto Networks XSOAR packs on our *<{MP_LINK}|Marketplace Site>*!"
        }
    }


def build_message(packs):
    blocks = [build_header_block(len(packs))]

    for pack in packs[:3]:
        blocks.append(get_divider_block())
        blocks.extend(build_pack_blocks(pack))

    blocks.append(get_divider_block())
    blocks.append(get_bottom_block())

    return json.dumps({
        "blocks": blocks
    })


def main():
    args = demisto.args()
    index_folder_path = extract_index(args)
    new_packs = get_new_packs(args, index_folder_path)
    last_run = datetime.now().strftime(DATE_FORMAT)
    message = build_message(new_packs)
    return_results(CommandResults(
        outputs=new_packs,
        outputs_prefix='Pack',
        readable_output=tableToMarkdown(
            name=f'New Released Packs from {args["last_message_time_str"]}',
            t=new_packs,
            headers=['name', 'id', 'author', 'description', 'price', 'support']
        )
    ))
    return_results(CommandResults(
        outputs=last_run,
        outputs_prefix='LastRun',
        readable_output=tableToMarkdown(
            name='Last Run',
            t=last_run,
            headers=['LastRun']
        )
    ))
    return_results(CommandResults(
        outputs=message,
        outputs_prefix='Message',
        readable_output=tableToMarkdown(
            name="Slack blocks json",
            t=message,
            headers=['Message']
        )
    ))


if __name__ in ('__builtin__', 'builtins', '__main__'):
    main()
