@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: reduce to 6 exchanges on Render free tier to save memory"
git push origin master:main --force
echo DONE
pause