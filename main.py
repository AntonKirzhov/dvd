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

connection = mysql.connector.connect(
	host='localhost',
	database='filesaver',
	user='root',
	password='root',
	auth_plugin='mysql_native_password'
)

views = {}

v1_router = APIRouter(prefix='/api')

accept_only_media = True
image_formats = [".jpeg", ".png", ".jpg", ".ico", ".gif", ".tif", ".webp", ".eps", ".svg", ".heic", ".heif", ".bmp", ".tiff", ".raw"]
video_formats = [".mp4", ".avi", ".mov", ".wmv", ".avhcd", ".flv", ".f4v", ".swf", ".mkv", ".webm"]
encrypter_password = "filesaver"

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

def compress(data):
	# Преобразуем шестнадцатеричную строку в байты
	bytes_data = bytes.fromhex(data)
	# Кодируем в base64 и убираем padding
	encoded = base64.b64encode(bytes_data).decode().rstrip('=')
	return encoded

def decompress(compressed_data):
	print(compressed_data)
	# Добавляем padding для base64 декодирования
	padding = '=' * ((4 - len(compressed_data) % 4) % 4)
	padded_data = compressed_data + padding
	# Декодируем из base64
	decoded = base64.b64decode(padded_data)
	# Преобразуем байты обратно в шестнадцатеричную строку
	return decoded.hex()

def encrypt_xor(message: str, secret: str) -> str:
	return crypto_xor(message, secret).encode('utf-8').hex()

def decrypt_xor(message_hex: str, secret: str) -> str:
	message = bytes.fromhex(message_hex).decode('utf-8')
	return crypto_xor(message, secret)

@app.on_event("startup")
async def on_startup():
	print('Startup event - initialising')
	app.include_router(v1_router)

@v1_router.post("/upload_file")
async def upload_file(life: str, files: List[UploadFile]):
	global connection
	existing_folders = os.listdir("uploaded")
	new_name = random.randint(0,999999999)
	while new_name in existing_folders:
		new_name = random.randint(0,999999999)
	os.mkdir(f"uploaded/{new_name}")
	try:
		connection.ping(reconnect=True)
	except:
		pass
	cursor = connection.cursor(dictionary=True, buffered=True)
	async with aiofiles.open(f"uploaded/{new_name}/life.txt", 'w') as out_file:
		await out_file.write(life)
	for file in files:
		type_file = "file"
		for ext in image_formats:
			if ext in file.filename:
				type_file = "image"
				break
		for ext in video_formats:
			if ext in file.filename:
				type_file = "video"
				break
		if accept_only_media:
			if type_file != "file":
				async with aiofiles.open(f"uploaded/{new_name}/{file.filename}", 'wb') as out_file:
					content = await file.read()  # async read
					await out_file.write(content)  # async write
					try:
						cursor.execute(f"INSERT INTO `processing_queue` (`dir_id`, `filename`) VALUES ('{new_name}', '{file.filename}')")
					except:
						pass
		else:
			async with aiofiles.open(f"uploaded/{new_name}/{file.filename}", 'wb') as out_file:
				content = await file.read()  # async read
				await out_file.write(content)  # async write
				if type_file != "file":
					try:
						cursor.execute(f"INSERT INTO `processing_queue` (`dir_id`, `filename`) VALUES ('{new_name}', '{file.filename}')")
					except:
						pass

	connection.commit()
	cursor.close()
	return compress(encrypt_xor(str(new_name), encrypter_password))
@v1_router.get("/get_info")
async def get_info(id: str, view: bool = False):
	global connection
	encrypted_id = id
	if len(id) <= 0:
		return 404
	else:
		id = decrypt_xor(decompress(str(id)), encrypter_password)
		print(id)

		if view == True:
			if f"{id}" in views:
				views[f"{id}"] += 1
			else:
				views[f"{id}"] = 1

		try:
			connection.ping(reconnect=True)
		except:
			pass
		cursor = connection.cursor(dictionary=True, buffered=True)
		cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
		cursor.execute(f"SELECT * FROM `processing_queue` WHERE `dir_id` = '{id}' AND `status` = 'processing'")
		is_process = cursor.fetchone()
		cursor.close()
		if is_process != None:
			return 401

		path = f"uploaded/{id}"
		if os.path.isdir(path):
			async with aiofiles.open(f"{path}/life.txt", "r") as read_file:
				content = await read_file.read()
				if 'infinity' in content:
					expires_in = "infinity"
				else:
					if "." in content:
						expires_in = datetime.utcfromtimestamp(int(content[0:content.index(".")])).strftime('%Y-%m-%d %H:%M:%S')
					else:
						expires_in = datetime.utcfromtimestamp(int(content)).strftime('%Y-%m-%d %H:%M:%S')
				json = {}
				json['created'] = os.stat(path).st_mtime
				json['expires_in'] = expires_in
				json['files_count'] = 0
				json['size'] = 0
				json['views'] = views[f"{id}"]
				json['files'] = []
				for file in os.listdir(path):
					local_path = path + "/" + file
					if os.path.isfile(local_path) and not f"{id}.zip" in local_path and not "life.txt" in local_path:
						json['files_count'] += 1
						local_size = os.path.getsize(local_path)
						json['size'] += local_size
						filename = os.path.basename(local_path)
						type_file = "file"
						for ext in image_formats:
							if ext in local_path:
								type_file = "image"
								break
						for ext in video_formats:
							if ext in local_path:
								type_file = "video"
								break
						json['files'].append({filename: f"https://dvd.black/api/get_file?id={encrypted_id}&file_name={filename}", "type_file": type_file, "file_size": local_size})

				return json
		else:
			return 404

@v1_router.get("/get_file")
async def get_file(id: str, file_name: str):
	if id.isnumeric() == False:
		id = decrypt_xor(decompress(str(id)), encrypter_password)
	path = f"uploaded/{id}/{file_name}"
	if os.path.isfile(path):
		return FileResponse(path=path, filename=file_name)
	else:
		return JSONResponse(status_code=404, content="Error")

@v1_router.get("/delete_dir")
async def delete_dir(id: str):
	id = decrypt_xor(decompress(str(id)), encrypter_password)
	path = f"uploaded/{id}"
	if path != "uploaded/":
		try:
			shutil.rmtree(path)
			return JSONResponse(status_code=200, content="Succesfull")
		except Exception as e:
			print(e)
			return JSONResponse(status_code=404, content="Error")

@v1_router.get("/test")
async def test():
	return "11111"
@v1_router.get("/get_files")
async def get_files(id: str):
	id = decrypt_xor(decompress(str(id)), encrypter_password)
	path = f"uploaded/{id}"
	if os.path.isdir(path):
		zip_path = f"{path}/{id}.zip"
		print(zip_path)
		if os.path.isfile(zip_path) == False:
			print("create")
			zf = zipfile.ZipFile(zip_path, "w")
			files = os.listdir(path)
			for file in files:
				filepath = path + "/" + file
				if os.path.isfile(filepath) and not ".zip" in filepath and not ".txt" in filepath:
					zf.write(filepath, file)
			zf.close()
		return FileResponse(path=zip_path, filename=f"{id}.zip")
	else:
		return JSONResponse(status_code=404, content="Error")