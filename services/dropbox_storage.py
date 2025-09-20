import dropbox
from pathlib import Path

class DropboxError(Exception):
    pass

def upload_run_to_dropbox(run_id: str, run_dir: Path, token: str, parent_path: str = "/") -> str:
    """
    Загружает все файлы из run_dir в Dropbox, создаёт папку run_id
    и возвращает публичную ссылку на неё.
    """
    try:
        dbx = dropbox.Dropbox(token)

        # Папка для этого запуска
        dropbox_folder = f"{parent_path.rstrip('/')}/{run_id}"
        dbx.files_create_folder_v2(dropbox_folder)

        # Загружаем все файлы
        for path in run_dir.iterdir():
            if path.is_file():
                dropbox_path = f"{dropbox_folder}/{path.name}"
                with open(path, "rb") as f:
                    dbx.files_upload(
                        f.read(),
                        dropbox_path,
                        mode=dropbox.files.WriteMode.overwrite,
                    )

        # Делаем шаринг ссылки на папку
        link = dbx.sharing_create_shared_link_with_settings(dropbox_folder).url
        return link.replace("?dl=0", "?dl=1")  # чтобы скачивалось сразу
    except Exception as e:
        raise DropboxError(str(e))
