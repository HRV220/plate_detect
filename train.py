# train.py
from ultralytics import YOLO
import torch

def train_model():
    # --- НАСТРОЙКИ ОБУЧЕНИЯ ---
    
    # 1. Выбираем базовую модель. 's' - small, хороший баланс.
    PRETRAINED_MODEL = 'yolov8s-obb.pt' 
    
    # 2. Путь к нашему файлу data.yaml.
    DATASET_CONFIG_PATH = 'dataset/data.yaml'
    
    # 3. Количество эпох обучения. 50 - хорошее начало для такого датасета.
    # Если метрики будут продолжать расти, можно будет дообучить.
    EPOCHS = 50
    
    # 4. Размер изображений, к которому они будут приводиться.
    # 640 - стандарт для YOLOv8. Можно увеличить до 1024 для поиска мелких объектов,
    # но это потребует больше видеопамяти. Начнем с 640.
    IMAGE_SIZE = 640

    # 5. Размер батча. Зависит от VRAM вашей видеокарты.
    # Для RTX 3060 6GB попробуем 8. Если будет ошибка "CUDA out of memory", уменьшите до 4.
    BATCH_SIZE = 8
    
    # 6. Название проекта. YOLO создаст папку runs/detect/number_plate_s_model
    PROJECT_NAME = 'number_plate_s_model'
    
    # ---------------------------

    # Проверяем доступность GPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Используется устройство: {device}")
    if device == 'cpu':
        print("ВНИМАНИЕ: Обучение на CPU будет очень долгим!")

    # Загружаем предобученную модель
    model = YOLO(PRETRAINED_MODEL)

    print("Начало обучения модели...")
    
    # Запускаем обучение
    results = model.train(
        data=DATASET_CONFIG_PATH,
        epochs=EPOCHS,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        project=PROJECT_NAME,
        device=device,
        exist_ok=True, # Позволяет перезаписывать существующий проект
        workers=0  # <-- ВОТ ЭТО ИЗМЕНЕНИЕ

    )

    print("Обучение завершено!")
    print(f"Результаты сохранены в папке: {results.save_dir}")
    print("Лучшая модель сохранена как 'best.pt' внутри папки 'weights'.")

if __name__ == '__main__':
    train_model()