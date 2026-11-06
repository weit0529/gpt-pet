"""Build a reproducible offline release using only the Python standard library."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'pet.json', 'spritesheet.webp', 'install.ps1', 'preview.html',
    'README.md', 'README.en.md', 'LICENSE', 'CHANGELOG.md', 'docs/SECURITY-AUDIT.md',
    'docs/images/contact-sheet.jpg', 'docs/images/idle.webp',
    'docs/images/running.webp', 'docs/images/jumping.webp', 'docs/images/review.webp',
)


def validate():
    for name in FILES:
        path = ROOT / name
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError(f'Missing file or symbolic link: {name}')
    manifest = json.loads((ROOT / 'pet.json').read_text(encoding='utf-8'))
    if (manifest.get('id'), manifest.get('spriteVersionNumber'), manifest.get('spritesheetPath')) != (
        'gpt-pet', 2, 'spritesheet.webp'
    ):
        raise ValueError('Invalid pet manifest')
    sheet = (ROOT / 'spritesheet.webp').read_bytes()
    if len(sheet) < 25 or sheet[:4] != b'RIFF' or sheet[8:16] != b'WEBPVP8L' or sheet[20] != 0x2f:
        raise ValueError('Expected a static lossless WebP atlas')
    if struct.unpack_from('<I', sheet, 4)[0] + 8 != len(sheet):
        raise ValueError('Invalid WebP container length')
    bits = struct.unpack_from('<I', sheet, 21)[0]
    if (1 + (bits & 0x3fff), 1 + ((bits >> 14) & 0x3fff)) != (1536, 2288):
        raise ValueError('Invalid atlas dimensions')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='1.0.0')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', args.version):
        parser.error('Version must be a semantic version such as 1.0.0')
    validate()
    payloads = {}
    for name in sorted(FILES):
        data = (ROOT / name).read_bytes()
        if Path(name).suffix in ('.md', '.html', '.json', '.ps1') or name == 'LICENSE':
            data = data.replace(b'\r\n', b'\n')
            if name.endswith('.ps1'):
                data = data.replace(b'\n', b'\r\n')
        payloads[name] = data
    payloads['SHA256SUMS.txt'] = ''.join(
        f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in payloads.items()
    ).encode('utf-8')
    output = ROOT / 'dist'
    if output.is_symlink():
        raise ValueError('dist must not be a symbolic link')
    output.mkdir(exist_ok=True)
    archive = output / f'gpt-pet-v{args.version}.zip'
    checksum = output / 'SHA256SUMS.txt'
    if archive.is_symlink() or checksum.is_symlink():
        raise ValueError('Release outputs must not be symbolic links')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in sorted(payloads.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 8, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, data, compresslevel=9)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or set(bundle.namelist()) != set(payloads):
            raise ValueError('Release archive validation failed')
        for name, data in payloads.items():
            if bundle.read(name) != data:
                raise ValueError(f'Release content mismatch: {name}')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_bytes(f'{digest}  {archive.name}\n'.encode('utf-8'))
    print(f'Built {archive.name}: {archive.stat().st_size:,} bytes; {len(payloads)} files')
    print(f'SHA256: {digest}')


if __name__ == '__main__':
    main()
