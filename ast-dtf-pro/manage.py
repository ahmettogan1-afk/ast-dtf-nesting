import getpass
import hashlib
import json
import os
import re
import secrets
import sys
from backend import store

if len(sys.argv)!=3 or sys.argv[1]!='create-user':raise SystemExit('Kullanım: python manage.py create-user ast')
user=sys.argv[2]
if not re.fullmatch(r'[A-Za-z0-9_.-]{1,60}',user):raise SystemExit('Kullanıcı adı geçersiz.')
password=getpass.getpass('Parola (en az 12 karakter): ')
if len(password)<12:raise SystemExit('Parola en az 12 karakter olmalı.')
if password!=getpass.getpass('Parola tekrar: '):raise SystemExit('Parolalar eşleşmiyor.')
store.init();f=store.DATA/'users.json';users=json.loads(f.read_text()) if f.exists() else {}
salt=secrets.token_bytes(16);users[user]=salt.hex()+':'+hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
f.write_text(json.dumps(users));os.chmod(f,0o600)
print('Kullanıcı kaydedildi:',user)
