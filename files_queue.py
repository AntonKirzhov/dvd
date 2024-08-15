import mysql.connector
import threading
import os
import random
import string
from heic2png import HEIC2PNG
from PIL import Image

connection = mysql.connector.connect(
	host='localhost',
	database='filesaver',
	user='root',
	password='root',
	auth_plugin='mysql_native_password'
)

image_formats = [".jpeg", ".png", ".jpg", ".ico", ".gif", ".tif", ".webp", ".eps", ".svg", ".heic", ".heif", ".bmp", ".tiff", ".raw"]

def set_interval(func, sec):
	def func_wrapper():
		set_interval(func, sec)
		func()
	t = threading.Timer(sec, func_wrapper)
	t.start()
	return t

def compress_img(image_name, new_filename, quality=90, new_size_ratio=0.9, width=None, height=None):
	if ".heic" in image_name or ".heif" in image_name:
		heic_img = HEIC2PNG(image_name, quality=50)
		heic_img.save(output_image_file_path=new_filename)
	else:
		img = Image.open(image_name)
		try:
			img.save(new_filename, quality=quality, optimize=True)
		except OSError:
			img = img.convert("RGB")
			img.save(new_filename, quality=quality, optimize=True)

def generate_random_string(length):
    letters = string.ascii_letters + string.digits
    rand_string = ''.join(random.choice(letters) for i in range(length))
    return rand_string

def process_queue():
	try:
		connection.ping(reconnect=True)
	except:
		pass
	cursor = connection.cursor(dictionary=True, buffered=True)
	cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
	cursor.execute(f"SELECT * FROM `processing_queue` WHERE `status` = 'processing' ORDER BY `id` ASC")
	tasks = cursor.fetchall()
	if len(tasks) <= 29:
		cursor.execute(f"SELECT * FROM `processing_queue` WHERE `status` = 'created' ORDER BY `id` ASC")
		task = cursor.fetchone()

		if task != None:
			dir_id = task['dir_id']
			filename = task['filename']
			is_image = False
			cursor.execute(f"UPDATE `processing_queue` SET `status` = 'processing' WHERE `id` = '{task['id']}'")
			connection.commit()
			
			try:
				for ext in image_formats:
					if ext in task['filename']:
						is_image = True
						break

				if is_image:
					if ".heif" in filename:
						os.rename(f"/root/file_backend/uploaded/{dir_id}/{filename}", f"/root/file_backend/uploaded/{dir_id}/{filename.replace(".heif", ".heic")}")
						filename = filename.replace(".heif", ".heic")
					old_name = f"/root/file_backend/uploaded/{dir_id}/{filename}"
					new_name = f"/root/file_backend/uploaded/{dir_id}/{filename[0:filename.index('.')]}{generate_random_string(5)}.png"
					compress_img(old_name, new_name, 50)
					if old_name != new_name:
						os.remove(old_name)
					cursor.execute(f"DELETE FROM `processing_queue` WHERE `id` = '{task['id']}'")
				else:
					old_name = f"/root/file_backend/uploaded/{dir_id}/{filename}"
					print(old_name)
					new_name = f"/root/file_backend/uploaded/{dir_id}/{filename[0:filename.index('.')]}{generate_random_string(5)}.mp4"
					os.system(f'ffmpeg -i "{old_name}" -vf "scale=-2:720" -c:v libx264 -preset slow -crf 28 -c:a aac -b:a 128k -movflags +faststart "{new_name}"')
					if old_name != new_name:
						os.remove(old_name)
					cursor.execute(f"DELETE FROM `processing_queue` WHERE `id` = '{task['id']}'")
			except Exception as e:
				print(e)
				cursor.execute(f"DELETE FROM `processing_queue` WHERE `id` = '{task['id']}'")

	connection.commit()
	cursor.close()

set_interval(process_queue, 5)