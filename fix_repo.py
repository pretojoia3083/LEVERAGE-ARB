import subprocess, os
os.chdir(r"C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB")

files = ['leverage_arb.db', 'servidor.log', 'deploy.bat', 'deploy_nuvem.bat', 'deploy_nuvem.py', 'fix_repo.py']
for f in files:
    r = subprocess.run(['git', 'rm', '--cached', '-f', f], capture_output=True, text=True)
    msg = r.stdout.strip() or r.stderr.strip()
    print(f'{f}: {msg}')

subprocess.run(['git', 'add', '.'], capture_output=True)
r = subprocess.run(['git', 'commit', '-m', 'fix: remove db log scripts from repo'], capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())

r = subprocess.run(['git', 'push', 'origin', 'master:main', '--force'], capture_output=True, text=True, timeout=25)
print(r.stdout.strip() or r.stderr.strip())
print('DONE')
