#!/usr/bin/env python

import json
import os
import re
import shutil
from typing import List

import jinja2
import yaml
from paka import cmark


def parse_md_file(path, header_only=False):
    with open(path, 'r') as f:
        if not f.readline().startswith('---'):
            raise SystemError(f'not started by `---`: {path}')

        i = 0
        lines = []
        line = f.readline()
        while not line.startswith('---'):
            if i > 50:
                raise SystemError('not reached to `---` after 50 lines')
            lines.append(line)
            line = f.readline()
            i += 1

        page = yaml.load(''.join(lines), Loader=yaml.FullLoader)
        if not header_only:
            page['content'] = cmark.to_html(f.read())

        return page


class Folder:
    pattern = re.compile(r'^\d+\.(?P<name>.+)')

    def __init__(self, path, name=''):
        self.path: str = path
        self.name = name
        self.is_index: bool = False
        self.index: dict = {}
        self.parent: Folder = None
        self.folders: List[Folder] = []
        self.files: List[tuple] = []

        self._scan()

    def __repr__(self):
        return f"<Folder '{self.path}'>"

    @staticmethod
    def get_name(name):
        m = Folder.pattern.match(name)
        return m.group('name') if m else name

    def _scan(self):
        for x in os.scandir(self.path):
            if x.is_file() and x.name.endswith('.md'):
                if x.name == '_index.md':
                    self.is_index = True
                    self.index = parse_md_file(x.path, True)
                else:
                    name = os.path.splitext(self.get_name(x.name))[0]
                    self.files.append((x.name, name))
            elif x.is_dir() and not x.name.startswith('.'):
                folder = Folder(str(x.path), self.get_name(x.name))
                folder.parent = self
                self.folders.append(folder)

        self.files.sort(key=lambda x: x[0])
        self.folders.sort(key=lambda x: x.path)


class App:
    def __init__(self, config):
        self.config = config
        self.root: Folder = Folder(config['app']['content'])
        self.jinja = self._get_jinja()
        self.data = self._data_files()

    @staticmethod
    def mkdir(*args):
        path = os.path.join(*args)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

    def build(self):
        if os.path.exists(self.config['app']['public']):
            for x in os.scandir(self.config['app']['public']):
                if x.name == '.git':
                    continue
                elif x.is_dir():
                    shutil.rmtree(x.path)
                else:
                    os.unlink(x.path)
        self._build(self.root, self.config['app']['public'])
        self._copy_static_files()

    def _get_jinja(self):
        t_dir = os.path.join(self.config['app']['themes'],
                             self.config['theme'], 'layouts')
        return jinja2.Environment(loader=jinja2.FileSystemLoader(t_dir))

    def _build(self, folder: Folder, out_dir):
        if folder.is_index:
            page = parse_md_file(os.path.join(folder.path, '_index.md'))
            template = page.get('template', 'index.html')
            path = self.mkdir(out_dir, folder.name)
            self._write(template, path, folder, page)

        for f in folder.files:
            page = parse_md_file(os.path.join(folder.path, f[0]))
            template = page.get('template',
                                folder.index.get('files_template', 'page.html'))
            path = self.mkdir(out_dir, f[1])
            self._write(template, path, folder, page)

        for f in folder.folders:
            self._build(f, os.path.join(out_dir, f.name))

    def _write(self, template, path, folder, page):
        tpl = self.jinja.get_template(template)
        with open(os.path.join(path, 'index.html'), 'w') as out:
            out.write(tpl.render(
                config=self.config,
                root=self.root,
                data=self.data,
                folder=folder,
                page=page,
            ))

    def _data_files(self):
        data = {}
        for x in os.scandir(self.config['app']['data']):
            split = os.path.splitext(x.name)
            if x.is_file() and split[1] == '.json':
                with open(x.path, 'r') as f:
                    data[split[0]] = json.load(f)
        return data

    def _copy_static_files(self):
        def copy(src):
            for x in os.scandir(src):
                dst = os.path.join(self.config['app']['public'], x.name)
                if x.is_file():
                    shutil.copy(x.path, dst)
                elif x.is_dir():
                    shutil.copytree(x.path, dst)

        if os.path.exists(self.config['app']['static']):
            copy(self.config['app']['static'])

        src = os.path.join(self.config['app']['themes'],
                           self.config['theme'], 'static')
        if os.path.exists(src):
            copy(src)


def main():
    with open('config.yaml', 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    app = App(config)
    app.build()


main()
