# server/app/processor.py

import gc
import logging
import time
from typing import List

import cv2
import numpy as np
from ultralytics import YOLO

from app.core.config import settings

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

class NumberPlateCoverer:
    """
    Класс для детекции автомобильных номеров с помощью YOLOv8-OBB
    и наложения на них кастомного изображения.

    Оптимизирован для явного управления памятью в долгоживущих сервисах.
    """
    def __init__(self):
        logger.info("Инициализация NumberPlateCoverer...")
        self.device = settings.PROCESSING_DEVICE
        self.model = YOLO(settings.MODEL_PATH)
        self.model.to(self.device)
        logger.info(f"Модель {settings.MODEL_PATH} загружена на устройство: {self.device}.")

        # Загрузка изображения-заглушки
        try:
            self.cover_image = cv2.imread(settings.COVER_IMAGE_PATH, cv2.IMREAD_UNCHANGED)
            if self.cover_image is None:
                # cv2.imread молча возвращает None при ошибке
                raise FileNotFoundError(f"Файл не найден или имеет неверный формат: {settings.COVER_IMAGE_PATH}")
            
            # Проверка наличия альфа-канала
            self.has_alpha = len(self.cover_image.shape) == 3 and self.cover_image.shape[2] == 4
            if not self.has_alpha:
                logger.warning("Изображение-заглушка не имеет альфа-канала. Прозрачность может работать некорректно.")

            logger.info(f"Изображение-заглушка {settings.COVER_IMAGE_PATH} успешно загружено.")

        except Exception as e:
            logger.error(f"Критическая ошибка при загрузке изображения-заглушки: {e}", exc_info=True)
            raise

    def _get_destination_points(self, obb_box) -> np.ndarray:
        """Определяет 4 угловые точки для трансформации перспективы."""
        # numpy() переносит тензор с GPU/CPU на CPU в виде numpy-массива
        points = obb_box.xyxyxyxy[0].cpu().numpy().reshape(4, 2)
        
        rect = np.zeros((4, 2), dtype="float32")
        s = points.sum(axis=1)
        rect[0] = points[np.argmin(s)] # Top-left
        rect[2] = points[np.argmax(s)] # Bottom-right
        
        diff = np.diff(points, axis=1)
        rect[1] = points[np.argmin(diff)] # Top-right
        rect[3] = points[np.argmax(diff)] # Bottom-left
        
        return rect
        
    def _apply_cover_to_one_image(self, image: np.ndarray, obb_results) -> np.ndarray:
        """Применяет маски к одному изображению на основе результатов детекции."""
        if not obb_results:
            return image

        processed_image = image.copy()
        num_detections = len(obb_results)
        logger.debug(f"Наложение {num_detections} заглушек на изображение.")

        for box in obb_results:
            dest_points = self._get_destination_points(box)
            h, w = self.cover_image.shape[:2]
            src_points = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
            
            # Создаем и применяем трансформацию
            M = cv2.getPerspectiveTransform(src_points, dest_points)
            warped_cover = cv2.warpPerspective(
                self.cover_image, M, (processed_image.shape[1], processed_image.shape[0])
            )
            
            # Создаем маску для наложения
            if self.has_alpha:
                mask = warped_cover[:, :, 3]
            else:
                gray_warped = cv2.cvtColor(warped_cover, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(gray_warped, 1, 255, cv2.THRESH_BINARY)
            
            # Вырезаем область номера из оригинального изображения
            mask_inv = cv2.bitwise_not(mask)
            background = cv2.bitwise_and(processed_image, processed_image, mask=mask_inv)
            
            # Подготавливаем заглушку для наложения
            foreground_bgr = warped_cover[:, :, :3] if self.has_alpha else warped_cover
            foreground = cv2.bitwise_and(foreground_bgr, foreground_bgr, mask=mask)
            
            # Накладываем заглушку
            processed_image = cv2.add(background, foreground.astype(processed_image.dtype))
            
        return processed_image

    def cover_plate(self, image: np.ndarray) -> np.ndarray:
        """
        Одиночная обработка: Находит номера на изображении и накладывает заглушку.
        """
        logger.info("Запуск одиночной обработки изображения.")
        start_time = time.time()
        
        try:
            # results - это сложный объект, содержащий тензоры на self.device
            results = self.model(image, device=self.device, verbose=False)
            obb_results = results[0].obb
            processed_image = self._apply_cover_to_one_image(image, obb_results)
        finally:
            # ЯВНОЕ УПРАВЛЕНИЕ РЕСУРСАМИ
            # Удаляем ссылки на большие объекты, чтобы сборщик мусора их подобрал.
            # Особенно важны тензоры PyTorch, которые могут удерживать память на GPU.
            del results
            del obb_results
            # Принудительно запускаем сборщик мусора. Это может вызвать небольшую
            # задержку, но гарантирует освобождение памяти, что критично для стабильности.
            gc.collect() 
            logger.debug("Ресурсы после одиночной обработки освобождены.")

        end_time = time.time()
        logger.info(f"Одиночная обработка завершена за {end_time - start_time:.4f} секунд.")
        
        return processed_image
        
    def cover_plates_batch(self, images: List[np.ndarray], batch_size: int = 16, imgsz: int = 640) -> List[np.ndarray]:
        """
        Пакетная обработка: Находит номера на списке изображений и накладывает заглушки.
        """
        if not images:
            return []

        num_images = len(images)
        logger.info(f"Запуск пакетной обработки для {num_images} изображений (батч: {batch_size}).")
        start_time = time.time()
        
        processed_images = []
        results_batch = None  # Инициализируем для блока finally

        try:
            # results_batch может занимать очень много памяти (особенно на GPU)
            results_batch = self.model(
                images, device=self.device, verbose=False, batch=batch_size, imgsz=imgsz
            )
            
            for original_image, results in zip(images, results_batch):
                obb_results = results.obb
                processed_image = self._apply_cover_to_one_image(original_image, obb_results)
                processed_images.append(processed_image)
        
        finally:
            # ЯВНОЕ УПРАВЛЕНИЕ РЕСУРСАМИ
            # Это самый важный блок. results_batch - самый крупный потребитель памяти.
            del results_batch
            # Принудительный запуск сборщика мусора для освобождения памяти GPU и RAM
            # после обработки целого батча.
            gc.collect()
            logger.debug("Ресурсы после пакетной обработки освобождены.")

        end_time = time.time()
        total_time = end_time - start_time
        time_per_image = total_time / num_images if num_images > 0 else 0
        logger.info(
            f"Пакетная обработка {num_images} изображений завершена за {total_time:.4f} сек. "
            f"({time_per_image:.4f} сек/изображение)."
        )

        return processed_images