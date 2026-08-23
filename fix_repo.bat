@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: add more exchanges on cloud, increase timeout"
git push origin master:main --force
echo DONE
pause