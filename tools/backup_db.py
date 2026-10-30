"""Online SQLite backup including committed WAL data. Never overwrite a destination."""
import argparse, sqlite3
from pathlib import Path

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('source',type=Path); parser.add_argument('destination',type=Path)
 a=parser.parse_args()
 if not a.source.is_file(): parser.error('Source does not exist')
 if a.destination.exists(): parser.error('Destination already exists')
 a.destination.parent.mkdir(parents=True,exist_ok=True)
 # Exclusive create avoids accidental overwrite, even with concurrent commands.
 with a.destination.open('xb'): pass
 source=sqlite3.connect(a.source.resolve().as_uri()+'?mode=ro',uri=True)
 destination=sqlite3.connect(a.destination)
 try:
  source.backup(destination)
  if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('Integrity check failed')
 finally: destination.close(); source.close()
 print('Backup verified:',a.destination)
if __name__=='__main__': main()
