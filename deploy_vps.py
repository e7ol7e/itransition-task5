"""Deploy only Task 5; add its independent Caddy listener, with rollback."""
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path('/root/itransition/task5')
CADDY=Path('/etc/caddy/Caddyfile')
BLOCK='''
# Task 5 mining observatory via Cloudflare Tunnel: task5.evgeniy.win.
:5004 {
    bind 127.0.0.1
    handle /submission/* {
        root * /var/www/itransition-task5
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:5005
    }
}
'''


def run(*args):
    return subprocess.run(args,cwd=ROOT,check=True)


def main():
    original=CADDY.read_text()
    previous=subprocess.run(['docker','image','inspect','itransition-task5:prod','--format','{{.Id}}'],capture_output=True,text=True)
    if previous.returncode==0:
        run('docker','tag',previous.stdout.strip(),'itransition-task5:rollback')
    try:
        run('docker','compose','build')
        run('docker','compose','up','-d','--wait','--wait-timeout','120')
        if ':5004 {' not in original:
            CADDY.write_text(original.rstrip()+'\n'+BLOCK)
            run('systemctl','reload','caddy')
        with urllib.request.urlopen('http://127.0.0.1:5004/healthz',timeout=10) as response:
            assert b'ok' in response.read()
        print('Task 5 healthy on Caddy :5004 and Docker :5005. Other applications untouched.')
    except Exception:
        if CADDY.read_text()!=original:
            CADDY.write_text(original)
            run('systemctl','reload','caddy')
        if previous.returncode==0:
            run('docker','tag','itransition-task5:rollback','itransition-task5:prod')
            run('docker','compose','up','-d')
        raise


if __name__=='__main__':main()
