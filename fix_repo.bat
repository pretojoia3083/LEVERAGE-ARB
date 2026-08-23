@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: busca direta via API publica USDT/BRL por exchange"
git push origin master:main --force
echo DONE
pause