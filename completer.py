# Copyright (C) 2017 Jakub Bujak
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

from ycmd.completers.completer import Completer
from ycmd import responses

import glob
import re


class NianioLangCompleter(Completer):
    def __init__(self, user_options):
        super(NianioLangCompleter, self).__init__(user_options)

    def SupportedFiletypes(self):
        return ['nl']

    def ComputeCandidatesInner(self, request_data):
        caret_index = request_data['start_column']
        line = request_data['line_bytes'].decode('utf-8')
        last_token = line[:caret_index+1].split(' ')[-1].split('(')[-1].strip()
        path = request_data._request['working_dir']
        filepath = request_data._request['filepath']
        file_contents = request_data._request['file_data'][filepath]['contents']
        line_number = request_data._request['line_num']
        ret = []
        self.path = path

        if '::' in last_token:
            return self._FindFunctions(path, last_token.lstrip('@'))
        elif '->' in last_token:
            return self._FindFields(path, file_contents, line_number, last_token)
        return []

    def _FindFunctions(self, path, last_token):
        module_name = last_token.split(':')[0]
        filename =  module_name + '.nl'
        function_prefix = last_token.split(':')[2]
        module_files = glob.glob(path + '/**/' + filename, recursive=True)
        if len(module_files) == 0:
            return []
        reg = 'def ' + module_name + '::(' + function_prefix + '[^(]*)'
        with open(module_files[0]) as module:
            matches = re.findall(reg, module.read())
            return [responses.BuildCompletionData(match) for match in matches]

    def _FindFields(self, path, file_contents, line_number, last_token):
        line_index = line_number - 1
        lines = file_contents.split('\n')
        chain = last_token.split('->')
        chain = list(map(self._TrimChainElement, chain))
        var_name = chain[0]
        reg = var_name + ' : @?([a-zA-Z:_]*)'
        var_type = ''

        res = []
        for i in range(line_index, -1, -1):
            line = lines[i].strip()
            matches = re.findall(reg, line)
            if len(matches) > 0:
                var_type = matches[0]
                break
            if line.startswith('def '):
                break
        if var_type == '':
            return []
        type_def = self._TypeDefinition(path, var_type)
        res.extend(self._FindFieldsForChain(type_def, chain[1:]))

        return [responses.BuildCompletionData(
                insertion_text = elem['text'],
                extra_menu_info = elem['type']) for elem in res]

    def _TrimChainElement(self, element):
        element.strip()
        if element.find('[') != -1:
            element = element[0:element.find('[')]
        if element.find('{') != -1:
            element = element[0:element.find('{')]
        return element
        

    def _FindFieldsForChain(self, type_def, chain):
        if len(chain) == 1 and type_def.startswith('ptd::rec'):
            return [{
                    'text': a['key'],
                    'type': a['type']
                } for a in self._GetRecFields(type_def)]
        if type_def.startswith('ptd::sim'):
            return []
        if type_def.startswith('ptd::arr') or type_def.startswith('ptd::hash'):
            beg = type_def.find('(')
            end = self._GetClosingIndex(type_def, beg)
            inner_type_def = type_def[beg+1:end-1]
            return self._FindFieldsForChain(inner_type_def, chain[0:])
        if type_def.startswith('ptd::rec'):
            fields = self._GetRecFields(type_def)
            for field in fields:
                if field['key'] == chain[0]:
                    return self._FindFieldsForChain(field['value'], chain[1:])
        return []

    def _TypeDefinition(self, path, function):
        module_name = function.split(':')[0]
        filename =  module_name + '.nl'
        module_files = []
        depth = 0
        module_files = glob.glob(path + '/**/' + filename, recursive=True)
        if len(module_files) == 0:
            return ''
        reg = 'def ' + function + '[^\{]*(\{.*)'
        with open(module_files[0]) as module:
            matches = re.findall(reg, module.read().replace('\n', ''), re.DOTALL)
            if len(matches) == 0:
                return ''
        res = matches[0][0:self._GetClosingIndex(matches[0], 0)]
        res = res.replace('return', '')
        res = res.replace(' ', '').replace('\t', '')
        res = res.lstrip('{').rstrip('}')
        return res

    def _GetRecFields(self, rec):
        res = []
        pos = len('ptd::rec({')
        while pos < len(rec):
            el = {}
            key_end_pos = rec[pos:].find('=>')
            if key_end_pos == -1:
                break
            el['key'] = rec[pos:pos+key_end_pos]
            pos += key_end_pos + len('=>')
            if rec[pos] == '@':
                value_end_pos = rec[pos:].find(',')
                if value_end_pos == -1:
                    break
                el['value'] = self._TypeDefinition(self.path, rec[pos+1:pos+value_end_pos])
                el['type'] = rec[pos:pos+value_end_pos]
                pos += value_end_pos + 1
            else:
                opening_index = rec[pos:].find('(')
                if opening_index == -1:
                    break
                closing_index = self._GetClosingIndex(rec[pos:], opening_index)
                if closing_index == -1:
                    break
                el['value'] = rec[pos:pos+closing_index+1]
                el['type'] = el['value'][0:el['value'].find('(')]
                pos += closing_index
                pos += rec[pos:].find(',') + 1
            res.append(el)
        return res

    def _GetClosingIndex(self, text, index):
        opening = text[index]
        if opening == '{':
            closing = '}'
        elif opening == '(':
            closing = ')'
        elif opening == '[':
            closing = ']'
        else:
            return index
        count = 0
        for i in range(index, len(text)):
            if text[i] == opening:
                count += 1
            elif text[i] == closing:
                count -= 1
            if count == 0:
                return i
        return -1
