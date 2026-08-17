#!/bin/bash

# Переходим в папку бота
cd /root/XFI_CONNECT || exit

# Проверяем, инициализирован ли git
if [ ! -d ".git" ]; then
    echo "Инициализация Git-репозитория..."
    git init
    git branch -M main
    git remote add origin https://github.com/deilja/XFI_CONNECT.git
fi

# Добавляем все изменения
git add .

# Запрашиваем текст коммита (или используем дефолтный)
echo "Введите сообщение для коммита (или нажмите Enter для стандартного):"
read commit_message
if [ -z "$commit_message" ]; then
    commit_message="Update bot code"
fi

git commit -m "$commit_message"

# Отправляем на GitHub
git push -u origin main

echo "Код успешно отправлен на GitHub!"
