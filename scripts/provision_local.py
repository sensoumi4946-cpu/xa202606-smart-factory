import argparse
import os
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('.'))
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    paths = [root / '.env', root / 'backend.env', root / 'connectivity.env']
    if any(p.exists() for p in paths):
        parser.error('Refusing to overwrite existing credentials; use a new directory.')
    api, signing, fuseki = (secrets.token_hex(32) for _ in range(3))
    active = "ACTIVE_PROTOCOL_DEVICES='" + '{"mqtt":["ESP32_001"],"rest":["ESP32_002","ESP32_003"],"modbus":["ESP32_005"],"opcua":["ESP32_004"]}' + "'\n"
    common = f'API_KEY={api}\nCOMMAND_SIGNING_KEY={signing}\nHARDWARE_PROFILE=real\n' + active
    contents = [common + f'FUSEKI_ADMIN_PASSWORD={fuseki}\n', common + 'SEMANTIC_WRITE_ENABLED=false\n', f'API_KEY={api}\nBACKEND_URL=http://127.0.0.1:8000\n' + active]
    for path, text in zip(paths, contents):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
    print('Created private local configuration files. Configure hardware endpoints before starting.')


if __name__ == '__main__':
    main()
