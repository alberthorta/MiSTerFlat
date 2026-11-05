import os
import tempfile
import unittest

from mistermanager.saves import SaveError, Saves, merge_cores


class SavesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fat = os.path.join(self.tmp.name, 'fat')
        self.state = os.path.join(self.tmp.name, 'state')
        self.put('saves/SNES/Super Mario World (U).sav', b'\x01' * 2048)
        self.put('saves/SNES/.hidden', b'x')
        self.put('saves/CD-i/CD-i.sav', b'\x02' * 8192)
        os.makedirs(os.path.join(self.fat, 'saves', 'GBA'))
        self.put('savestates/SNES/Super Mario World (U)_1.ss', b'\x03' * 100)
        self.put('savestates/SNES/Super Mario World (U)_1.png', b'png')
        self.saves = Saves(self.fat, self.state)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, data):
        path = os.path.join(self.fat, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)

    def test_list(self):
        out = self.saves.list('SNES')
        self.assertEqual([s['file'] for s in out['saves']], ['Super Mario World (U).sav'])
        self.assertEqual(out['saves'][0]['size'], 2048)
        self.assertEqual(out['states'], [dict(out['states'][0], file='Super Mario World (U)_1.ss',
                                              game='Super Mario World (U)', slot=1)])
        with self.assertRaises(SaveError):
            self.saves.list('Nothing')

    def test_folders_and_merge(self):
        folders = self.saves.folders()
        self.assertEqual(folders['SNES'], {'saves': 1, 'states': 1})
        self.assertEqual(folders['GBA'], {'saves': 0, 'states': 0})
        installed = [{'id': 'SNES', 'name': 'SNES', 'options': 12}, {'id': 'GBA', 'name': 'GBA', 'options': 9},
                     {'id': 'NES', 'name': 'NES', 'options': 5}]
        merged = {c['id']: c for c in merge_cores(installed, folders)}
        self.assertEqual((merged['SNES']['saves'], merged['SNES']['states']), (1, 1))
        self.assertEqual(merged['GBA']['folder'], 'GBA')
        self.assertIsNone(merged['NES']['folder'])
        # A folder with saves but no core in the catalog becomes a core of its own.
        self.assertEqual(merged['CD-i'], {'id': 'CD-i', 'name': 'CD-i', 'options': 0, 'folder': 'CD-i',
                                          'saves': 1, 'states': 0})

    def test_names_cannot_leave_the_folder(self):
        for core, name in (('SNES', '../CD-i/CD-i.sav'), ('..', 'saves'), ('SNES', '.hidden'),
                           ('SNES', 'missing.sav'), ('../saves/SNES', 'Super Mario World (U).sav')):
            with self.assertRaises(SaveError):
                self.saves.read('saves', core, name)

    def test_replace_keeps_a_backup(self):
        self.saves.replace('SNES', 'Super Mario World (U).sav', b'new')
        self.assertEqual(self.saves.read('saves', 'SNES', 'Super Mario World (U).sav'), b'new')
        backups = os.listdir(os.path.join(self.state, 'backups', 'saves', 'saves', 'SNES'))
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self.state, 'backups', 'saves', 'saves', 'SNES', backups[0]), 'rb') as f:
            self.assertEqual(f.read(), b'\x01' * 2048)
        with self.assertRaises(SaveError):
            self.saves.replace('SNES', 'Super Mario World (U).sav', b'')

    def test_delete_keeps_a_backup(self):
        self.saves.delete('states', 'SNES', 'Super Mario World (U)_1.ss')
        self.assertEqual(self.saves.list('SNES')['states'], [])
        self.assertTrue(os.listdir(os.path.join(self.state, 'backups', 'saves', 'states', 'SNES')))
        with self.assertRaises(SaveError):
            self.saves.delete('states', 'SNES', 'Super Mario World (U)_1.png')


if __name__ == '__main__':
    unittest.main()
