import subprocess, os

os.chdir(r"C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB")

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout: print(r.stdout.strip())
    if r.stderr: print(r.stderr.strip())
    return r.returncode

print("=== LIMPANDO GIT ===")

# Remover arquivos que nao devem estar no repo
files_to_remove = ['leverage_arb.db', 'servidor.log', 'deploy.bat', 'deploy_nuvem.bat', 'deploy_nuvem.py', 'leverage_arb.db-wal', 'leverage_arb.db-shm']
for f in files_to_remove:
    run(['git', 'rm', '--cached', '-f', f])

print("\n=== STATUS ===")
run(['git', 'status'])

print("\n=== ADD TUDO ===")
run(['git', 'add', '.'])

print("\n=== COMMIT ===")
run(['git', 'commit', '-m', 'fix: add static folder, remove db/log from repo'])

print("\n=== PUSH ===")
run(['git', 'push', '-u', 'origin', 'main', '--force'])

print("\n=== PRONTO ===")
