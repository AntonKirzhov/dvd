import os
import aiofiles
import random
import zipfile
import mysql.connector
import shutil
import base64
from fastapi import FastAPI, Request, UploadFile, File, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import datetime

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=['*'],
	allow_credentials=False,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Инициализация коннекта с базой данных
connection = mysql.connector.connect(
	host='localhost',
	database='filesaver',
	user='root',
	password='root',
	auth_plugin='mysql_native_password'
)

# Объект, в котором хранится кол-во просмотров страниц файлов
views = {}

# Инициализация апи роутера с префиксом /api
v1_router = APIRouter(prefix='/api')

# Переменная, отвечающая за функцию "отсекания" файлов не являющихся медиа, если False - принимает любой файл
accept_only_media = True
# Блок переменных, в которых перечисляются форматы видео и аудио
image_formats = [".jpeg", ".png", ".jpg", ".ico", ".gif", ".tif", ".webp", ".eps", ".svg", ".heic", ".heif", ".bmp", ".tiff", ".raw"]
video_formats = [".mp4", ".avi", ".mov", ".wmv", ".avhcd", ".flv", ".f4v", ".swf", ".mkv", ".webm"]
# Переменная, несущая в себе пароль для шифрования XOR + HEX
encrypter_password = "filesaver"

# Функция, отвечающая за шифрование строки методом XOR
def crypto_xor(message: str, secret: str) -> str:
	new_chars = list()
	i = 0

	for num_chr in (ord(c) for c in message):
		num_chr ^= ord(secret[i])
		new_chars.append(num_chr)

		i += 1
		if i >= len(secret):
			i = 0

	return ''.join(chr(c) for c in new_chars)

# Функция, отвечающая за сжатие строки байтовым способом
def compress(data: str) -> str:
	# Преобразуем шестнадцатеричную строку в байты
	bytes_data = bytes.fromhex(data)
	# Кодируем в base64 и убираем padding
	encoded = base64.b64encode(bytes_data).decode().rstrip('=')
	return encoded

# Функция, отвечающая за расжатие строки байтовым способом
def decompress(compressed_data: str) -> str:
	print(compressed_data)
	# Добавляем padding для base64 декодирования
	padding = '=' * ((4 - len(compressed_data) % 4) % 4)
	padded_data = compressed_data + padding
	# Декодируем из base64
	decoded = base64.b64decode(padded_data)
	# Преобразуем байты обратно в шестнадцатеричную строку
	return decoded.hex()

# Функция, отвечающая за шифрование строки
def encrypt_xor(message: str, secret: str) -> str:
	return crypto_xor(message, secret).encode('utf-8').hex()

# Функция, отвечающая за дешифрование строки
def decrypt_xor(message_hex: str, secret: str) -> str:
	message = bytes.fromhex(message_hex).decode('utf-8')
	return crypto_xor(message, secret)

@app.on_event("startup")
async def on_startup():
	# Событие после инициализации фастапи
	print('Startup event - initialising')
	app.include_router(v1_router)

@v1_router.post("/upload_file")
async def upload_file(life: str, compress: bool, files: List[UploadFile]):
	# Приём файлов, их сохранение и обработка
	global connection
	existing_folders = os.listdir("uploaded")
	# Генерируем рандомное имя для новой директории
	new_name = random.randint(0,999999999)
	# Цикл проверки имени на уникальность
	while new_name in existing_folders:
		new_name = random.randint(0,999999999)
	# Создаем директорию,
	os.mkdir(f"uploaded/{new_name}")
	try:
		connection.ping(reconnect=True)
	except:
		pass
	# Инициализируем курсор для работы с базой данных
	cursor = connection.cursor(dictionary=True, buffered=True)
	# Создаем файл life.txt и записываем туда время жизни файлов
	async with aiofiles.open(f"uploaded/{new_name}/life.txt", 'w') as out_file:
		await out_file.write(life)
	for file in files:
		# Создаем файлы
		type_file = "file"
		for ext in image_formats:
			# Проверка, что файл - изображение
			if ext in file.filename:
				type_file = "image"
				break
		for ext in video_formats:
			# Проверка, что файл - видео
			if ext in file.filename:
				type_file = "video"
				break
		if accept_only_media:
			# Отсекаем не медиа файлы и создаем их
			if type_file != "file":
				async with aiofiles.open(f"uploaded/{new_name}/{file.filename}", 'wb') as out_file:
					content = await file.read()  # async read
					await out_file.write(content)  # async write
                    if compress:
					    try:
						    # Заносим файл в таблицу для последующего сжатия и обработки
						    cursor.execute(f"INSERT INTO `processing_queue` (`dir_id`, `filename`) VALUES ('{new_name}', '{file.filename}')")
					    except:
						    pass
		else:
			async with aiofiles.open(f"uploaded/{new_name}/{file.filename}", 'wb') as out_file:
				# Создаем все файлы
				content = await file.read()  # async read
				await out_file.write(content)  # async write
				if type_file != "file" and compress:
					# Проверка, что файл - медиа
					try:
						# Заносим файл в таблицу для последующего сжатия и обработки
						cursor.execute(f"INSERT INTO `processing_queue` (`dir_id`, `filename`) VALUES ('{new_name}', '{file.filename}')")
					except:
						pass

	# Коммитим изменения в базу и закрываем текущий курсор
	connection.commit()
	cursor.close()
	# Возвращаем зашифрованное сжатое имя директории
	return compress(encrypt_xor(str(new_name), encrypter_password))

@v1_router.post("/add_files")
async def add_files(id: str, files: List[UploadFile]):
	# Приём файлов, их сохранение и обработка
	global connection
	if len(id) <= 0:
		# Если id пустой - возврат 404
		return 404
	else:
		# Расшифровываем переданный ID директории для получения настоящего значения
		id = decrypt_xor(decompress(str(id)), encrypter_password)
		print(id)

		path = f"uploaded/{id}"
		# Проверяем, что директория существует
		if os.path.isdir(path):
			try:
				connection.ping(reconnect=True)
			except:
				pass
			# Инициализируем курсор для работы с базой данных
			cursor = connection.cursor(dictionary=True, buffered=True)
			for file in files:
				# Дозагружаем файлы
				type_file = "file"
				for ext in image_formats:
					# Проверка, что файл - изображение
					if ext in file.filename:
						type_file = "image"
						break
				for ext in video_formats:
					# Проверка, что файл - видео
					if ext in file.filename:
						type_file = "video"
						break
				if accept_only_media:
					# Отсекаем не медиа файлы и создаем их
					if type_file != "file":
						async with aiofiles.open(f"{path}/{file.filename}", 'wb') as out_file:
							content = await file.read()  # async read
							await out_file.write(content)  # async write
							try:
								# Заносим файл в таблицу для последующего сжатия и обработки
								cursor.execute(f"INSERT INTO `processing_queue` (`dir_id`, `filename`) VALUES ('{new_name}', '{file.filename}')")
							except:
								pass
				else:
					async with aiofiles.open(f"{path}/{file.filename}", 'wb') as out_file:
						# Создаем все файлы
						content = await file.read()  # async read
						await out_file.write(content)  # async write
						if type_file != "file":
							# Проверка, что файл - медиа
							try:
								# Заносим файл в таблицу для последующего сжатия и обработки
								cursor.execute(f"INSERT INTO `processing_queue` (`dir_id`, `filename`) VALUES ('{new_name}', '{file.filename}')")
							except:
								pass

			# Коммитим изменения в базу и закрываем текущий курсор
			connection.commit()
			cursor.close()
			# Возвращаем зашифрованное сжатое имя директории
			return JSONResponse(status_code=200, content="Succesfull")
		else:
			return JSONResponse(status_code=404, content="Error")

@v1_router.get("/get_info")
async def get_info(id: str, view: bool = False):
	# Получение информации о загруженной директории и её файлах
	global connection
	encrypted_id = id
	if len(id) <= 0:
		# Если id пустой - возврат 404
		return 404
	else:
		# Расшифровываем переданный ID директории для получения настоящего значения
		id = decrypt_xor(decompress(str(id)), encrypter_password)
		print(id)

		if view == True:
			# Если view == True, то засчитываем +1 просмотр
			if f"{id}" in views:
				views[f"{id}"] += 1
			else:
				views[f"{id}"] = 1

		try:
			connection.ping(reconnect=True)
		except:
			pass
		# Инициализация курсора для работы с базой данных
		cursor = connection.cursor(dictionary=True, buffered=True)
		cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
		# Получаем информацию о файлах из этой директории в процессинге обработки
		cursor.execute(f"SELECT * FROM `processing_queue` WHERE `dir_id` = '{id}' AND `status` = 'processing'")
		is_process = cursor.fetchone()
		cursor.close()
		if is_process != None:
			# Если происходит процесс сжатия, выдаем 401
			return 401

		path = f"uploaded/{id}"
		# Проверяем, что директория существует
		if os.path.isdir(path):
			async with aiofiles.open(f"{path}/life.txt", "r") as read_file:
				# Читаем файл со сроком жизни директории
				content = await read_file.read()
				if 'infinity' in content:
					# Формируем вывод срока жизни файла
					expires_in = "infinity"
				else:
					# Формируем вывод срока жизни файла
					if "." in content:
						expires_in = datetime.utcfromtimestamp(int(content[0:content.index(".")])).strftime('%Y-%m-%d %H:%M:%S')
					else:
						expires_in = datetime.utcfromtimestamp(int(content)).strftime('%Y-%m-%d %H:%M:%S')
				# Инициализируем объект и его параметры для отдачи на фронт
				json = {}
				json['created'] = os.stat(path).st_mtime
				json['expires_in'] = expires_in
				json['files_count'] = 0
				json['size'] = 0
				json['views'] = views[f"{id}"]
				json['files'] = []
				# Перебираем файлы в директории
				for file in os.listdir(path):
					# Формируем путь к файлам для более удобной работы
					local_path = path + "/" + file
					# Проверяем, что файл не life.txt и не сжатая директория
					if os.path.isfile(local_path) and not f"{id}.zip" in local_path and not "life.txt" in local_path:
						# Прибавляем файл в счетчик
						json['files_count'] += 1
						# Получаем размер файла
						local_size = os.path.getsize(local_path)
						# Прибавляем счетчик общего размера директории
						json['size'] += local_size
						# Получаем имя файла
						filename = os.path.basename(local_path)
						type_file = "file"
						for ext in image_formats:
							# Проверка, что файл - изображение
							if ext in local_path:
								type_file = "image"
								break
						for ext in video_formats:
							# Проверка, что файл - видео
							if ext in local_path:
								type_file = "video"
								break
						# Добавляем в список файлов текущий файл и информацию о нём
						json['files'].append({filename: f"https://dvd.black/api/get_file?id={encrypted_id}&file_name={filename}", "type_file": type_file, "file_size": local_size})
				# Возвращаем информацию о директории
				return json
		else:
			return 404

@v1_router.get("/get_file")
async def get_file(id: str, file_name: str):
	# Получение информации о файле
	if id.isnumeric() == False:
		# Если ID передан зашифрованынй - расшифровываем
		id = decrypt_xor(decompress(str(id)), encrypter_password)
	# Формируем путь для более удобной работы
	path = f"uploaded/{id}/{file_name}"
	if os.path.isfile(path):
		# Если есть файл, возвращаем его
		return FileResponse(path=path, filename=file_name)
	else:
		# Если файла нет, возвращаем ошибку
		return JSONResponse(status_code=404, content="Error")

@v1_router.get("/delete_dir")
async def delete_dir(id: str):
	# Удаление директории

	# Расшифровываем переданный ID
	id = decrypt_xor(decompress(str(id)), encrypter_password)
	# Формируем путь для более удобной работы
	path = f"uploaded/{id}"
	if path != "uploaded/":
		try:
			# Удаляем директорию
			shutil.rmtree(path)
			# Возвращаем статус 200
			return JSONResponse(status_code=200, content="Succesfull")
		except Exception as e:
			# Показываем и возвращаем ошибку
			print(e)
			return JSONResponse(status_code=404, content="Error")

@v1_router.get("/get_files")
async def get_files(id: str):
	# Скачать директорию 

	# Расшифровываем переданный ID
	id = decrypt_xor(decompress(str(id)), encrypter_password)
	# Формируем путь для более удобной работы
	path = f"uploaded/{id}"
	# Проверяем, что директория существует
	if os.path.isdir(path):
		# Формируем путь к сжатой в архив директории для более удобной работы
		zip_path = f"{path}/{id}.zip"
		# Проверяем, что сжатый архив не существует
		if os.path.isfile(zip_path) == False:
			# Создаем архив директории
			zf = zipfile.ZipFile(zip_path, "w")
			# Получаем список файлов
			files = os.listdir(path)
			# Перебираем каждый файл и добавляем его в архив
			for file in files:
				filepath = path + "/" + file
				if os.path.isfile(filepath) and not ".zip" in filepath and not ".txt" in filepath:
					zf.write(filepath, file)
			# Убираем архив из памяти и работы
			zf.close()
		# Возвращаем архив с помещенными внутрь файлами
		return FileResponse(path=zip_path, filename=f"{id}.zip")
	else:
		# Если директории нет, выводим ошибку
		return JSONResponse(status_code=404, content="Error")
