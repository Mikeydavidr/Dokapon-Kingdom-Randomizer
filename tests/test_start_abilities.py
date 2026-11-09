import struct
import unittest
from pathlib import Path

from dokapon_rando import start_abilities as sa
from dokapon_rando.exe import Exe, HexMod, foff

EXE = Path(r"G:\Programming\Dokapon-Workspace\ActualGame\DkkStm.exe")


class StartAbilitiesTest(unittest.TestCase):
    def test_cave_layout(self):
        cave = sa.build_cave(0x14044C5A0, sa.RUST, sa.WATERFALL)
        self.assertEqual(cave[:4], bytes.fromhex("83 7B 70 00"))
        skip = cave[5]
        self.assertEqual(cave[6 + skip:6 + skip + 5], bytes.fromhex("BA 04 00 00 00"))      # the displaced instruction follows the body
        rel = struct.unpack_from("<i", cave, len(cave) - 4)[0]
        self.assertEqual(0x14044C5A0 + len(cave) + rel, sa.RETURN_VA)                      # and the jump lands after it

    def test_ids_checked(self):
        with self.assertRaises(ValueError):
            sa.build_cave(0x14044C5A0, 40, None)

    @unittest.skipUnless(EXE.exists(), "needs the game exe")
    def test_applies_to_exe(self):
        exe = Exe(EXE.read_bytes())
        mod = HexMod()
        sa.apply_start_abilities(exe, mod)
        patched = mod.apply(exe.data)
        o = foff(sa.HOOK_VA)
        self.assertEqual(patched[o], 0xE9)
        try:
            import capstone
        except ImportError:
            return
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        cave_va = 0x14044C5A0
        text = [f"{i.mnemonic} {i.op_str}" for i in md.disasm(bytes(patched[foff(cave_va):foff(cave_va) + 48]), cave_va)][:7]
        self.assertEqual(text[0], "cmp dword ptr [rbx + 0x70], 0")
        self.assertIn("mov byte ptr [rbx + 0xc1], 0x17", text)
        self.assertIn("or dword ptr [rbx + 0x74], 0x800000", text)
        self.assertIn("mov byte ptr [rbx + 0xc2], 0x26", text)


if __name__ == "__main__":
    unittest.main()
