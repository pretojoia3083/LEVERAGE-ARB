import subprocess, os
os.chdir(r"C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB")
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if r.stdout: print(r.stdout.strip())
    if r.stderr: print(r.stderr.strip())
    return r.returncode

run(['git', 'rm', '--cached', '-f', 'fix_repo.py'])
run(['git', 'add', '.'])
run(['git', 'commit', '-m', 'fix: pin Python 3.12 for Render compatibility'])
run(['git', 'push', 'origin', 'master:main', '--force'])
print('DONE')
