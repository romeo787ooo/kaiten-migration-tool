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
        # Create a temporary directory for file downloads
        self.temp_dir = Path(tempfile.mkdtemp())

    def make_source_request(self, endpoint: str, method: str = "GET", json_data: Dict = None, params: Dict = None) -> Dict:
        url = f"{self.source_base_url}/{endpoint}"
        # st.write(f"Making SOURCE request: {method} {url}") # Optional: uncomment for deep debug
        # if params:
        #     st.write(f"With params: {json.dumps(params, indent=2)}")
        # if json_data:
        #     st.write(f"With data: {json.dumps(json_data, indent=2)}")
            
        try:
            response = requests.request(
                method,
                url,
                headers=self.source_headers,
                json=json_data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error in source request:")
            st.error(f"URL: {url}")
            st.error(f"Method: {method}")
            if params:
                st.error(f"Params: {params}")
            if json_data:
                st.error(f"Data: {json_data}")
            if hasattr(e.response, 'text'):
                st.error(f"Response: {e.response.text}")
            raise

    def make_target_request(self, endpoint: str, method: str = "GET", json_data: Dict = None, files: Dict = None) -> Dict:
        url = f"{self.target_base_url}/{endpoint}"
        # st.write(f"Making TARGET request: {method} {url}") # Optional: uncomment for deep debug
        # if json_data:
        #     st.write(f"With data: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
            
        headers = self.target_headers.copy()
        if files:
            # Remove Content-Type for multipart/form-data
            headers.pop("Content-Type", None)
            
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json_data if not files else None,
                files=files
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error in target request:")
            st.error(f"URL: {url}")
            st.error(f"Method: {method}")
            if json_data:
                # Use ensure_ascii=False to correctly display Cyrillic characters in error logs
                st.error(f"Data: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
            if hasattr(e.response, 'text'):
                st.error(f"Response: {e.response.text}")
            raise

    def get_card_files(self, card_id: int) -> List[Dict]:
        """Get all files attached to a card"""
        return self.make_source_request(f"cards/{card_id}/files")

    def download_file(self, file_url: str, file_name: str) -> str:
        """Download a file from source Kaiten instance"""
        response = requests.get(file_url, headers=self.source_headers)
        response.raise_for_status()
        
        file_path = self.temp_dir / file_name
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        return str(file_path)

    def upload_file_to_card(self, card_id: int, file_path: str, original_filename: str) -> Dict:
        """Upload a file to a card in target Kaiten instance"""
        with open(file_path, 'rb') as f:
            files = {
                'file': (original_filename, f, 'application/octet-stream')
            }
            return self.make_target_request(
                f"cards/{card_id}/files",
                method="POST",
                files=files
            )

    def get_card_checklists(self, card_id: int) -> List[Dict]:
        """Get all checklists for a card"""
        card = self.make_source_request(f"cards/{card_id}")
        return card.get('checklists', [])

    def create_card_checklist(self, card_id: int, title: str) -> Dict:
        """Create a new checklist on a card"""
        return self.make_target_request(
            f"cards/{card_id}/checklists",
            method="POST",
            json_data={"name": title}
        )

    def create_checklist_item(self, card_id: int, checklist_id: int, text: str, checked: bool = False) -> Dict:
        """Create a new checklist item"""
        return self.make_target_request(
            f"cards/{card_id}/checklists/{checklist_id}/items",
            method="POST",
            json_data={
                "text": text,
                "checked": checked
            }
        )

    def migrate_card_files(self, card_id: int, target_card_id: int, log_container):
        """Migrate all files from source card to target card"""
        try:
            # Get all files from source card
            files = self.get_card_files(card_id)
            
            for file in files:
                try:
                    # Download file from source
                    file_path = self.download_file(file['url'], file['name'])
                    
                    # Upload file to target
                    self.upload_file_to_card(target_card_id, file_path, file['name'])
                    
                    # Clean up temporary file
                    os.remove(file_path)
                except Exception as e:
                    log_container.error(f"Failed to migrate file {file['name']}: {str(e)}")
                    continue
                    
        except Exception as e:
            log_container.error(f"Failed to migrate files for card {card_id}: {str(e)}")

    def migrate_card_checklists(self, source_card_id: int, target_card_id: int, log_container):
        """Migrate all checklists from source card to target card"""
        try:
            source_card = self.make_source_request(f"cards/{source_card_id}")
            checklists = source_card.get('checklists', [])

            for checklist in checklists:
                try:
                    # Create new checklist on target card
                    new_checklist = self.create_card_checklist(target_card_id, checklist['name'])

                    # Migrate checklist items
                    for item in checklist.get('items', []):
                        self.create_checklist_item(
                            target_card_id,
                            new_checklist['id'],
                            item['text'],
                            item.get('checked', False)
                        )

                except Exception as e:
                    log_container.error(f"Failed to migrate checklist {checklist.get('name', '')}: {str(e)}")
                    continue

        except Exception as e:
            log_container.error(f"Failed to migrate checklists for card {source_card_id}: {str(e)}")

    def get_card_comments(self, card_id: int) -> List[Dict]:
        """Get all comments for a card"""
        return self.make_source_request(f"cards/{card_id}/comments")

    def create_card_comment(self, card_id: int, text: str) -> Dict:
        """Create a new comment on a card"""
        return self.make_target_request(
            f"cards/{card_id}/comments",
            method="POST",
            json_data={
                "text": text,
                "text_format_type_id": 1  # 1 - markdown format
            }
        )

    def __del__(self):
        """Cleanup temporary directory on object destruction"""
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            for file in self.temp_dir.iterdir():
                try:
                    file.unlink()
                except Exception:
                    pass
            try:
                self.temp_dir.rmdir()
            except Exception:
                pass

## >> ИЗМЕНЕНИЕ: Добавлена новая вспомогательная функция
def prepare_properties_for_migration(source_properties: Optional[Dict]) -> Optional[Dict]:
    """
    Подготавливает кастомные поля для миграции.
    Конвертирует сложные объекты (например, пользователей) в простой список ID,
    который ожидает API при создании карточки.
    """
    if not source_properties:
        return None

    prepared_props = {}
    for key, value in source_properties.items():
        # Проверяем, является ли значение списком словарей (как список пользователей)
        if isinstance(value, list) and value and isinstance(value[0], dict) and 'id' in value[0]:
            # Извлекаем только 'id' из каждого элемента списка
            prepared_props[key] = [item['id'] for item in value if 'id' in item]
        else:
            # Для простых значений (строка, число, список чисел) копируем как есть
            prepared_props[key] = value
            
    return prepared_props


## >> ИЗМЕНЕНИЕ: Функция migrate_cards полностью заменена на исправленную версию
def migrate_cards(migration_instance, cards_to_migrate, target_board_id, target_column_id, 
                 target_lane_id, progress_bar, status_text, log_container):
    """Функция для миграции выбранных карточек"""
    try:
        total_cards = len(cards_to_migrate)
        success_count = 0

        for i, (card_title, card) in enumerate(cards_to_migrate.items()):
            try:
                status_text.text(f"Миграция карточки: {card_title}")
                log_container.write(f"📋 Начало миграции карточки: {card_title}")
                
                # Подготовка кастомных полей для миграции
                log_container.write("🛠️ Подготовка кастомных полей...")
                prepared_properties = prepare_properties_for_migration(card.get('properties'))

                # Prepare card data
                new_card_data = {
                    "title": card['title'],
                    "description": card.get('description'),
                    "board_id": target_board_id,
                    "column_id": target_column_id,
                    "lane_id": target_lane_id,
                    "type_id": card.get('type_id'),
                    "size_text": card.get('size_text'),
                    "due_date": card.get('due_date'),
                    "asap": card.get('asap', False),
                    "properties": prepared_properties, # Используем очищенные данные
                    "expires_later": card.get('expires_later', False)
                }
                
                # Remove None values
                new_card_data = {k: v for k, v in new_card_data.items() if v is not None}
                
                # Create new card
                log_container.write("⭐ Создание новой карточки...")
                new_card = migration_instance.make_target_request(
                    "cards",
                    method="POST",
                    json_data=new_card_data
                )
                
                # Migrate tags if present
                if new_card and card.get('tags'):
                    try:
                        log_container.write("🏷️ Миграция тегов...")
                        source_tags = migration_instance.make_source_request(
                            f"cards/{card['id']}/tags"
                        )
                        
                        for tag in source_tags:
                            migration_instance.make_target_request(
                                f"cards/{new_card['id']}/tags",
                                method="POST",
                                json_data={
                                    "name": tag["name"],
                                    "color": tag["color"]
                                }
                            )
                    except Exception as e:
                        log_container.error(f"⚠️ Ошибка миграции тегов: {str(e)}")

                # Migrate comments
                try:
                    log_container.write("💬 Миграция комментариев...")
                    source_comments = migration_instance.get_card_comments(card['id'])
                    for comment in source_comments:
                        comment_text = f"**Комментарий от {comment.get('author', {}).get('full_name', 'Unknown')}**\n{comment['text']}"
                        migration_instance.create_card_comment(
                            new_card['id'],
                            comment_text
                        )
                except Exception as e:
                    log_container.error(f"⚠️ Ошибка миграции комментариев: {str(e)}")

                # Migrate files
                try:
                    log_container.write("📎 Миграция файлов...")
                    migration_instance.migrate_card_files(card['id'], new_card['id'], log_container)
                except Exception as e:
                    log_container.error(f"⚠️ Ошибка миграции файлов: {str(e)}")

                # Migrate checklists
                try:
                    log_container.write("✅ Миграция чек-листов...")
                    migration_instance.migrate_card_checklists(card['id'], new_card['id'], log_container)
                except Exception as e:
                    log_container.error(f"⚠️ Ошибка миграции чек-листов: {str(e)}")

                success_count += 1
                progress_bar.progress((i + 1) / total_cards)
                log_container.write(f"✨ Успешно мигрирована карточка: {card_title}")

            except Exception as e:
                log_container.error(f"❌ Ошибка при миграции карточки {card_title}: {str(e)}")

        status_text.text(f"Миграция завершена: {success_count} из {total_cards}")
        return success_count, total_cards

    except Exception as e:
        log_container.error(f"❌ Критическая ошибка: {str(e)}")
        return 0, total_cards

def main():
    st.set_page_config(
        page_title="🔄 Kaiten Migration Tool",
        page_icon="🔄",
        layout="wide"
    )

    st.title("🔄 Инструмент миграции карточек Kaiten")

    # Initialize session state
    if 'migration_instance' not in st.session_state:
        st.session_state.migration_instance = None
    if 'source_boards' not in st.session_state:
        st.session_state.source_boards = []
    if 'target_boards' not in st.session_state:
        st.session_state.target_boards = []
    if 'cards_cache' not in st.session_state:
        st.session_state.cards_cache = {}

    # Создаем колонки для source и target
    col1, col2 = st.columns(2)

    # Source configuration
    with col1:
        st.header("📤 Источник")
        source_domain = st.text_input("Домен источника", placeholder="example.kaiten.ru")
        source_space_id = st.text_input("Space ID источника")
        source_token = st.text_area("Token источника", placeholder="Вставьте token")

    # Target configuration
    with col2:
        st.header("📥 Назначение")
        target_domain = st.text_input("Домен назначения", placeholder="example.kaiten.ru")
        target_space_id = st.text_input("Space ID назначения")
        target_token = st.text_area("Token назначения", placeholder="Вставьте token")

    # Load boards button
    if st.button("🔄 Загрузить доски"):
        try:
            # Add .kaiten.ru if needed
            if source_domain and not source_domain.endswith('.kaiten.ru'):
                source_domain += '.kaiten.ru'
            if target_domain and not target_domain.endswith('.kaiten.ru'):
                target_domain += '.kaiten.ru'

            st.session_state.migration_instance = KaitenMigration(
                source_domain,
                target_domain,
                source_token,
                target_token
            )

            # Load boards
            st.session_state.source_boards = st.session_state.migration_instance.make_source_request(
                f"spaces/{source_space_id}/boards"
            )
            st.session_state.target_boards = st.session_state.migration_instance.make_target_request(
                f"spaces/{target_space_id}/boards"
            )

            st.success("Доски успешно загружены!")
        except Exception as e:
            st.error(f"Ошибка при загрузке досок: {str(e)}")

    # Display boards and migration interface if instance exists
    if st.session_state.migration_instance:
        # Create columns for source and target selection
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📋 Исходные доски и карточки")
            
            # Source board selection
            source_board = st.selectbox(
                "Выберите доску источника",
                options=[board['title'] for board in st.session_state.source_boards],
                key="source_board"
            )
            
            if source_board:
                selected_board = next((b for b in st.session_state.source_boards if b['title'] == source_board), None)
                
                if selected_board:
                    # Source column selection
                    source_column = st.selectbox(
                        "Выберите колонку источника",
                        options=[col['title'] for col in selected_board.get('columns', [])],
                        key="source_column"
                    )

                    if source_column:
                        selected_column = next((c for c in selected_board['columns'] if c['title'] == source_column), None)
                        if selected_column:
                            try:
                                # Load cards
                                with st.spinner("Загрузка карточек..."):
                                    cards = st.session_state.migration_instance.make_source_request(
                                        "cards",
                                        params={
                                            "space_id": source_space_id,
                                            "board_id": selected_board['id'],
                                            "column_id": selected_column['id']
                                        }
                                    )
                                st.session_state.cards_cache = {f"{card['title']} (ID: {card['id']})": card for card in cards}
                                
                                # Card selection
                                selected_cards = st.multiselect(
                                    "Выберите карточки для миграции",
                                    options=list(st.session_state.cards_cache.keys())
                                )

                                # Show preview for selected card
                                if selected_cards:
                                    preview_card_title = selected_cards[-1]
                                    preview_card = st.session_state.cards_cache[preview_card_title]
                                    st.text_area(
                                        f"Предпросмотр карточки: {preview_card_title}",
                                        value=json.dumps(preview_card, indent=2, ensure_ascii=False),
                                        height=200
                                    )

                            except Exception as e:
                                st.error(f"Ошибка при загрузке карточек: {str(e)}")

        with col2:
            st.subheader("📋 Целевые доски и колонки")
            
            # Target board selection
            target_board = st.selectbox(
                "Выберите доску назначения",
                options=[board['title'] for board in st.session_state.target_boards],
                key="target_board"
            )
            
            if target_board:
                selected_target_board = next((b for b in st.session_state.target_boards if b['title'] == target_board), None)
                
                if selected_target_board:
                    # Target column selection
                    target_column = st.selectbox(
                        "Выберите колонку назначения",
                        options=[col['title'] for col in selected_target_board.get('columns', [])],
                        key="target_column"
                    )

        # Migration section
        if 'selected_cards' in locals() and selected_cards and target_board and 'target_column' in locals() and target_column:
            st.subheader("📦 Миграция")
            
            if st.button("Начать миграцию выбранных карточек"):
                # Setup progress indicators
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_container_expander = st.expander("Показать лог миграции", expanded=True)
                log_container = log_container_expander.container()

                
                try:
                    # Get target board and column info
                    target_board_data = next(b for b in st.session_state.target_boards if b['title'] == target_board)
                    target_column_data = next(c for c in target_board_data['columns'] if c['title'] == target_column)
                    target_lane_id = target_board_data['lanes'][0]['id'] if target_board_data.get('lanes') else None

                    if not target_lane_id:
                        st.error("У целевой доски нет полос (lanes). Миграция невозможна.")
                        return

                    # Prepare cards for migration
                    cards_to_migrate = {title: st.session_state.cards_cache[title] for title in selected_cards}
                    
                    # Start migration
                    success_count, total_cards = migrate_cards(
                        st.session_state.migration_instance,
                        cards_to_migrate,
                        target_board_data['id'],
                        target_column_data['id'],
                        target_lane_id,
                        progress_bar,
                        status_text,
                        log_container
                    )

                    # Show final results
                    if success_count == total_cards and total_cards > 0:
                        st.success(f"Миграция успешно завершена! Перенесено {success_count} из {total_cards} карточек.")
                    elif success_count > 0:
                        st.warning(f"Миграция завершена с ошибками. Успешно перенесено {success_count} из {total_cards} карточек. Проверьте лог выше.")
                    else:
                        st.error(f"Миграция не удалась. Перенесено {success_count} из {total_cards} карточек. Проверьте лог выше.")

                except Exception as e:
                    st.error(f"Критическая ошибка при запуске миграции: {str(e)}")

if __name__ == "__main__":
    main()
