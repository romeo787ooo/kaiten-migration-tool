import streamlit as st
import requests
import json
from typing import Dict, List, Optional, Any
import os
from pathlib import Path
import tempfile

class KaitenMigration:
    def __init__(self, source_domain: str, target_domain: str, source_token: str, target_token: str):
        self.source_base_url = f"https://{source_domain}/api/latest"
        self.target_base_url = f"https://{target_domain}/api/latest"
        self.source_headers = {
            "Authorization": f"Bearer {source_token}",
            "Content-Type": "application/json"
        }
        self.target_headers = {
            "Authorization": f"Bearer {target_token}",
            "Content-Type": "application/json"
        }
        self.temp_dir = Path(tempfile.mkdtemp())

    def make_request(self, base_url: str, headers: Dict, endpoint: str, method: str = "GET", json_data: Dict = None, params: Dict = None, files: Dict = None) -> Any:
        url = f"{base_url}/{endpoint}"
        
        request_headers = headers.copy()
        if files:
            request_headers.pop("Content-Type", None)

        try:
            response = requests.request(
                method,
                url,
                headers=request_headers,
                json=json_data if not files else None,
                params=params,
                files=files
            )
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error in request to {url} ({method})")
            if hasattr(e.response, 'text'):
                st.error(f"Response: {e.response.text}")
            raise

    def make_source_request(self, *args, **kwargs):
        return self.make_request(self.source_base_url, self.source_headers, *args, **kwargs)

    def make_target_request(self, *args, **kwargs):
        return self.make_request(self.target_base_url, self.target_headers, *args, **kwargs)

    def get_card_files(self, card_id: int) -> List[Dict]:
        return self.make_source_request(f"cards/{card_id}/files")

    def download_file(self, file_url: str, file_name: str) -> str:
        response = requests.get(file_url, headers=self.source_headers)
        response.raise_for_status()
        file_path = self.temp_dir / file_name
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return str(file_path)

    def upload_file_to_card(self, card_id: int, file_path: str, original_filename: str) -> Dict:
        with open(file_path, 'rb') as f:
            files = {'file': (original_filename, f, 'application/octet-stream')}
            return self.make_target_request(f"cards/{card_id}/files", method="POST", files=files)

    def get_card_checklists(self, card_id: int) -> List[Dict]:
        card = self.make_source_request(f"cards/{card_id}")
        return card.get('checklists', [])

    def create_card_checklist(self, card_id: int, title: str) -> Dict:
        return self.make_target_request(f"cards/{card_id}/checklists", method="POST", json_data={"name": title})

    def create_checklist_item(self, card_id: int, checklist_id: int, text: str, checked: bool = False) -> Dict:
        return self.make_target_request(f"cards/{card_id}/checklists/{checklist_id}/items", method="POST", json_data={"text": text, "checked": checked})

    def migrate_card_files(self, card_id: int, target_card_id: int, log_container):
        try:
            files = self.get_card_files(card_id)
            for file in files:
                try:
                    file_path = self.download_file(file['url'], file['name'])
                    self.upload_file_to_card(target_card_id, file_path, file['name'])
                    os.remove(file_path)
                except Exception as e:
                    log_container.error(f"Failed to migrate file {file['name']}: {str(e)}")
        except Exception as e:
            log_container.error(f"Failed to migrate files for card {card_id}: {str(e)}")

    def migrate_card_checklists(self, source_card_id: int, target_card_id: int, log_container):
        try:
            checklists = self.get_card_checklists(source_card_id)
            for checklist in checklists:
                try:
                    new_checklist = self.create_card_checklist(target_card_id, checklist['name'])
                    for item in checklist.get('items', []):
                        self.create_checklist_item(target_card_id, new_checklist['id'], item['text'], item.get('checked', False))
                except Exception as e:
                    log_container.error(f"Failed to migrate checklist {checklist.get('name', '')}: {str(e)}")
        except Exception as e:
            log_container.error(f"Failed to migrate checklists for card {source_card_id}: {str(e)}")

    def get_card_comments(self, card_id: int) -> List[Dict]:
        return self.make_source_request(f"cards/{card_id}/comments")

    def create_card_comment(self, card_id: int, text: str) -> Dict:
        return self.make_target_request(f"cards/{card_id}/comments", method="POST", json_data={"text": text, "text_format_type_id": 1})

    def __del__(self):
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            for f in self.temp_dir.iterdir(): f.unlink()
            try:
                self.temp_dir.rmdir()
            except OSError: # Ignore errors if dir is not empty, though it should be
                pass


def remap_and_prepare_properties(source_props: Optional[Dict], source_fields: List[Dict], target_fields: List[Dict], log_container) -> Optional[Dict]:
    if not source_props:
        return None

    source_id_to_name = {f['id']: f['name'] for f in source_fields}
    target_name_to_id = {f['name']: f['id'] for f in target_fields}
    
    prepared_props = {}
    log_container.write("🔄 Сопоставление кастомных полей...")

    for key, value in source_props.items():
        if not key.startswith('id_'): continue
        
        source_field_id = int(key.replace('id_', ''))
        source_field_name = source_id_to_name.get(source_field_id)
        
        if not source_field_name:
            log_container.warning(f"🤔 Поле с ID {source_field_id} не найдено в исходной доске, пропущено.")
            continue
            
        target_field_id = target_name_to_id.get(source_field_name)
        
        if not target_field_id:
            log_container.warning(f"🤔 Поле '{source_field_name}' не найдено на целевой доске, пропущено.")
            continue
            
        cleaned_value = value
        if isinstance(value, list) and value and isinstance(value[0], dict) and 'id' in value[0]:
            cleaned_value = [item['id'] for item in value if 'id' in item]
            
        target_key = f"id_{target_field_id}"
        prepared_props[target_key] = cleaned_value
        log_container.write(f"✅ Сопоставлено поле: '{source_field_name}' (ID {source_field_id} -> {target_field_id})")

    return prepared_props


## >> НОВАЯ ФУНКЦИЯ: для загрузки всех карточек с пагинацией
def get_all_cards_from_column(migration_instance: KaitenMigration, space_id: str, board_id: int, column_id: int) -> List[Dict]:
    """
    Загружает все карточки из указанной колонки, используя пагинацию.
    """
    all_cards = []
    limit = 100
    offset = 0
    
    while True:
        params = {
            "space_id": space_id,
            "board_id": board_id,
            "column_id": column_id,
            "limit": limit,
            "offset": offset
        }
        
        batch_of_cards = migration_instance.make_source_request("cards", params=params)
        
        if not batch_of_cards:
            break  # Больше карточек нет, выходим из цикла
        
        all_cards.extend(batch_of_cards)
        offset += limit
        
    return all_cards


def migrate_cards(migration_instance, cards_to_migrate, source_board_id, target_board_id, target_column_id, target_lane_id, progress_bar, status_text, log_container):
    try:
        log_container.write("ℹ️ Загрузка информации о полях исходной доски...")
        source_board_details = migration_instance.make_source_request(f"boards/{source_board_id}")
        source_custom_fields = source_board_details.get('custom_fields', [])
        
        log_container.write("ℹ️ Загрузка информации о полях целевой доски...")
        target_board_details = migration_instance.make_target_request(f"boards/{target_board_id}")
        target_custom_fields = target_board_details.get('custom_fields', [])

        total_cards = len(cards_to_migrate)
        success_count = 0

        for i, (card_title, card) in enumerate(cards_to_migrate.items()):
            try:
                status_text.text(f"Миграция карточки: {card_title}")
                log_container.write(f"--- 📋 Начало миграции карточки: {card_title} ---")
                
                prepared_properties = remap_and_prepare_properties(
                    card.get('properties'), 
                    source_custom_fields, 
                    target_custom_fields,
                    log_container
                )

                new_card_data = {
                    "title": card['title'], "description": card.get('description'), "board_id": target_board_id,
                    "column_id": target_column_id, "lane_id": target_lane_id, "type_id": card.get('type_id'),
                    "size_text": card.get('size_text'), "due_date": card.get('due_date'), "asap": card.get('asap', False),
                    "properties": prepared_properties, "expires_later": card.get('expires_later', False)
                }
                
                new_card_data = {k: v for k, v in new_card_data.items() if v is not None}
                
                log_container.write("⭐ Создание новой карточки...")
                new_card = migration_instance.make_target_request("cards", method="POST", json_data=new_card_data)
                log_container.success(f"✔️ Карточка '{card_title}' успешно создана с ID {new_card['id']}")
                
                if new_card:
                    if card.get('tags'):
                        log_container.write("🏷️ Миграция тегов...")
                        source_tags = migration_instance.make_source_request(f"cards/{card['id']}/tags")
                        for tag in source_tags:
                            migration_instance.make_target_request(f"cards/{new_card['id']}/tags", method="POST", json_data={"name": tag["name"], "color": tag["color"]})
                    
                    log_container.write("💬 Миграция комментариев...")
                    source_comments = migration_instance.get_card_comments(card['id'])
                    for comment in source_comments:
                        comment_text = f"**Комментарий от {comment.get('author', {}).get('full_name', 'Unknown')}** ({comment.get('created', '')}):\n\n{comment['text']}"
                        migration_instance.create_card_comment(new_card['id'], comment_text)

                    log_container.write("📎 Миграция файлов...")
                    migration_instance.migrate_card_files(card['id'], new_card['id'], log_container)

                    log_container.write("✅ Миграция чек-листов...")
                    migration_instance.migrate_card_checklists(card['id'], new_card['id'], log_container)

                success_count += 1
                progress_bar.progress((i + 1) / total_cards)
                log_container.write(f"✨ Успешно мигрирована карточка: {card_title}")

            except Exception as e:
                log_container.error(f"❌ Ошибка при миграции карточки {card_title}: {str(e)}")

        status_text.text(f"Миграция завершена: {success_count} из {total_cards}")
        return success_count, total_cards

    except Exception as e:
        log_container.error(f"❌ Критическая ошибка: {str(e)}")
        return 0, len(cards_to_migrate)

def main():
    st.set_page_config(page_title="🔄 Kaiten Migration Tool", page_icon="🔄", layout="wide")
    st.title("🔄 Инструмент миграции карточек Kaiten")

    if 'migration_instance' not in st.session_state:
        st.session_state.migration_instance = None
    if 'source_boards' not in st.session_state:
        st.session_state.source_boards = []
    if 'target_boards' not in st.session_state:
        st.session_state.target_boards = []
    if 'cards_cache' not in st.session_state:
        st.session_state.cards_cache = {}

    col1, col2 = st.columns(2)

    with col1:
        st.header("📤 Источник")
        source_domain = st.text_input("Домен источника", placeholder="yourcompany.kaiten.ru")
        source_space_id = st.text_input("ID пространства источника")
        source_token = st.text_area("Token источника", placeholder="Вставьте токен")

    with col2:
        st.header("📥 Назначение")
        target_domain = st.text_input("Домен назначения", placeholder="yourcompany.kaiten.ru")
        target_space_id = st.text_input("ID пространства назначения")
        target_token = st.text_area("Token назначения", placeholder="Вставьте токен")

    if st.button("🔄 Загрузить доски"):
        if not all([source_domain, source_space_id, source_token, target_domain, target_space_id, target_token]):
            st.warning("Пожалуйста, заполните все поля конфигурации.")
        else:
            try:
                st.session_state.migration_instance = KaitenMigration(source_domain, target_domain, source_token, target_token)
                with st.spinner("Загрузка досок..."):
                    st.session_state.source_boards = st.session_state.migration_instance.make_source_request(f"spaces/{source_space_id}/boards")
                    st.session_state.target_boards = st.session_state.migration_instance.make_target_request(f"spaces/{target_space_id}/boards")
                st.success("Доски успешно загружены!")
            except Exception as e:
                st.error(f"Ошибка при загрузке досок: {str(e)}")
                st.session_state.migration_instance = None

    if st.session_state.migration_instance:
        col1, col2 = st.columns(2)
        selected_cards = []

        with col1:
            st.subheader("📋 Исходные доски и карточки")
            source_board_titles = [b['title'] for b in st.session_state.source_boards]
            source_board_title = st.selectbox("Выберите доску источника", options=source_board_titles, key="source_board")
            
            if source_board_title:
                selected_board = next((b for b in st.session_state.source_boards if b['title'] == source_board_title), None)
                if selected_board:
                    column_titles = [c['title'] for c in selected_board.get('columns', [])]
                    source_column_title = st.selectbox("Выберите колонку источника", options=column_titles, key="source_column")
                    
                    ## >> ИЗМЕНЕНИЕ: Логика загрузки карточек заменена на вызов функции с пагинацией
                    if st.button("Загрузить карточки из колонки"):
                        selected_column = next((c for c in selected_board['columns'] if c['title'] == source_column_title), None)
                        if selected_column:
                            try:
                                with st.spinner("Загрузка карточек (может занять время для больших досок)..."):
                                    # Вызываем новую функцию для загрузки ВСЕХ карточек
                                    cards = get_all_cards_from_column(
                                        st.session_state.migration_instance,
                                        source_space_id,
                                        selected_board['id'],
                                        selected_column['id']
                                    )
                                    st.session_state.cards_cache = {f"{c['title']} (ID: {c['id']})": c for c in cards}
                                
                                st.success(f"Загружено {len(st.session_state.cards_cache)} карточек.")
                                if len(st.session_state.cards_cache) >= 100:
                                    st.info("Была применена постраничная загрузка для получения всех карточек.")

                            except Exception as e:
                                st.error(f"Ошибка при загрузке карточек: {str(e)}")
        
        if st.session_state.cards_cache:
            with col1:
                selected_cards = st.multiselect("Выберите карточки для миграции", options=list(st.session_state.cards_cache.keys()))
                if selected_cards:
                    preview_card = st.session_state.cards_cache[selected_cards[-1]]
                    with st.expander("Предпросмотр последней выбранной карточки (JSON)"):
                        st.json(preview_card)

        with col2:
            st.subheader("📋 Целевые доски и колонки")
            target_board_titles = [b['title'] for b in st.session_state.target_boards]
            target_board_title = st.selectbox("Выберите доску назначения", options=target_board_titles, key="target_board")
            
            if target_board_title:
                selected_target_board = next((b for b in st.session_state.target_boards if b['title'] == target_board_title), None)
                if selected_target_board:
                    target_column_titles = [c['title'] for c in selected_target_board.get('columns', [])]
                    target_column_title = st.selectbox("Выберите колонку назначения", options=target_column_titles, key="target_column")
        
        if selected_cards and 'target_column_title' in locals() and target_column_title:
            st.subheader("🚀 Запуск миграции")
            if st.button("Начать миграцию выбранных карточек"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_expander = st.expander("Показать лог миграции", expanded=True)
                log_container = log_expander.container()
                
                try:
                    source_board_id = next(b['id'] for b in st.session_state.source_boards if b['title'] == source_board_title)
                    target_board_data = next(b for b in st.session_state.target_boards if b['title'] == target_board_title)
                    target_column_data = next(c for c in target_board_data['columns'] if c['title'] == target_column_title)
                    target_lane_id = target_board_data['lanes'][0]['id'] if target_board_data.get('lanes') else None

                    if not target_lane_id:
                        st.error("У целевой доски нет дорожек (lanes). Миграция невозможна.")
                        return

                    cards_to_migrate = {title: st.session_state.cards_cache[title] for title in selected_cards}
                    
                    success_count, total_cards = migrate_cards(
                        st.session_state.migration_instance, cards_to_migrate, source_board_id, target_board_data['id'],
                        target_column_data['id'], target_lane_id, progress_bar, status_text, log_container
                    )

                    if success_count == total_cards and total_cards > 0:
                        st.success(f"Миграция успешно завершена! Перенесено {success_count} из {total_cards} карточек.")
                    elif success_count > 0:
                        st.warning(f"Миграция завершена с ошибками. Успешно перенесено {success_count} из {total_cards} карточек.")
                    else: st.error(f"Миграция не удалась. Перенесено {success_count} из {total_cards} карточек.")
                except Exception as e:
                    st.error(f"Критическая ошибка при запуске миграции: {str(e)}")

if __name__ == "__main__":
    main()
