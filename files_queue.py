import mysql.connector
import threading
import os
import random
import string
from heic2png import HEIC2PNG
from PIL import Image

# Инициализация соединения с базой данных
connection = mysql.connector.connect(
	host='localhost',
	database='filesaver',
	user='root',
	password='root',
	auth_plugin='mysql_native_password'
)

# Список форматов изображений
image_formats = [".jpeg", ".png", ".jpg", ".ico", ".gif", ".tif", ".webp", ".eps", ".svg", ".heic", ".heif", ".bmp", ".tiff", ".raw"]

def set_interval(func, sec):
	# Функция, задающая интервал выполнения другой функции
	def func_wrapper():
		set_interval(func, sec)
		func()
	t = threading.Timer(sec, func_wrapper)
	t.start()
	return t

def compress_img(image_name, new_filename, quality=90):
	# Функция, отвечающая за сжатие изображения в другой формат, чистку метаданных и уменьшение веса
	
	# Проверка, что файл .heic или .heif
	if ".heic" in image_name or ".heif" in image_name:
		# Используем библиотеку для работы с этими файлами и сжимаем файл
		heic_img = HEIC2PNG(image_name, quality=50)
		# Сохраняем сжатый файл
		heic_img.save(output_image_file_path=new_filename)
	else:
		# Открываем изображение для работы с ним
		img = Image.open(image_name)
		try:
			# Сохраняем сжатое изображение
			img.save(new_filename, quality=quality, optimize=True)
		except OSError:
			# Конвертируем изображение в RGB
			img = img.convert("RGB")
			# Сохраняем сжатое изображение
			img.save(new_filename, quality=quality, optimize=True)

def generate_random_string(length):
	# Функция генерации рандомной строки длиной в  length символов
    
	# Объявление массива с буквами и цифрами
    letters = string.ascii_letters + string.digits
    # Генерация рандомной строки
    rand_string = ''.join(random.choice(letters) for i in range(length))
    return rand_string

def process_queue():
	# Функция, отвечающая за процесс сжатия файлов
	try:
		connection.ping(reconnect=True)
	except:
		pass
	# Объявление курсора для работы с базой данных
	cursor = connection.cursor(dictionary=True, buffered=True)
	cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
	# Получаем текущие задачи на сжатие
	cursor.execute(f"SELECT * FROM `processing_queue` WHERE `status` = 'processing' ORDER BY `id` ASC")
	tasks = cursor.fetchall()
	# Проверяем, что задач в процессе сжатия менее 30
	if len(tasks) <= 29:
		# Получаем следующую задачу на очереди
		cursor.execute(f"SELECT * FROM `processing_queue` WHERE `status` = 'created' ORDER BY `id` ASC")
		task = cursor.fetchone()

		# Проверяем, есть ли задача
		if task != None:
			# Объявляем переменные для более удобной работы
			dir_id = task['dir_id']
			filename = task['filename']
			is_image = False
			# Ставим текущей задаче статус - в процессе
			cursor.execute(f"UPDATE `processing_queue` SET `status` = 'processing' WHERE `id` = '{task['id']}'")
			connection.commit()
			
			try:
				for ext in image_formats:
					# Проверяем, является ли файл изображением
					if ext in task['filename']:
						is_image = True
						break

				# Если файл изображение
				if is_image:
					if ".heif" in filename:
						# Если файл .heif - переименовываем его в .heic
						os.rename(f"/root/file_backend/uploaded/{dir_id}/{filename}", f"/root/file_backend/uploaded/{dir_id}/{filename.replace(".heif", ".heic")}")
						filename = filename.replace(".heif", ".heic")
					# Строка со старым именем файла
					old_name = f"/root/file_backend/uploaded/{dir_id}/{filename}"
					# Строка с новым именем файла
					new_name = f"/root/file_backend/uploaded/{dir_id}/{filename[0:filename.index('.')]}{generate_random_string(5)}.png"
					# Сжимаем изображение
					compress_img(old_name, new_name, 50)
					if old_name != new_name:
						# Если имена после сжатия не совпадают, удаляем изначальный файл
						os.remove(old_name)
					# Удаляем задачу из базы данных
					cursor.execute(f"DELETE FROM `processing_queue` WHERE `id` = '{task['id']}'")
				# Если файл видео
				else:
					# Строка со старым именем файла
					old_name = f"/root/file_backend/uploaded/{dir_id}/{filename}"
					# Строка с новым именем файла
					new_name = f"/root/file_backend/uploaded/{dir_id}/{filename[0:filename.index('.')]}{generate_random_string(5)}.mp4"
					# Сжимаем видео посредством вызова ffmpeg
					os.system(f'ffmpeg -i "{old_name}" -vf "scale=-2:720" -c:v libx264 -preset slow -crf 28 -c:a aac -b:a 128k -movflags +faststart "{new_name}"')
					if old_name != new_name:
						# Если имена после сжатия не совпадают, удаляем изначальный файл
						os.remove(old_name)
					# Удаляем задачу из базы данных
					cursor.execute(f"DELETE FROM `processing_queue` WHERE `id` = '{task['id']}'")
			except Exception as e:
				print(e)
				# В случае ошибки, удаляем задачу из базы данных
				cursor.execute(f"DELETE FROM `processing_queue` WHERE `id` = '{task['id']}'")

	# Коммитим изменения в базу и закрываем текущий курсор
	connection.commit()
	cursor.close()

# Ставим интервал выполнения функции process_queue на 5 секунд
set_interval(process_queue, 5)