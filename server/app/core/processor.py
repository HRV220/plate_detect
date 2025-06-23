import logging
import time
import cv2
import numpy as np
from ultralytics import YOLO
from typing import List
from app.core.config import settings

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

class NumberPlateCoverer:
    """
    Класс для детекции автомобильных номеров с помощью YOLOv8-OBB
    и наложения на них кастомного изображения.
    Поддерживает одиночную и пакетную обработку.
    """
    def __init__(self):
        logger.info("Инициализация NumberPlateCoverer...")
        self.device = settings.PROCESSING_DEVICE
        self.model = YOLO(settings.MODEL_PATH)
        self.model.to(self.device)
        logger.info(f"Модель {settings.MODEL_PATH} загружена на устройство {self.device}.")

        self.cover_image = cv2.imread(settings.COVER_IMAGE_PATH, cv2.IMREAD_UNCHANGED)
        if self.cover_image is None:
            logger.error(f"Не удалось загрузить заглушку: {settings.COVER_IMAGE_PATH}")
            raise FileNotFoundError(f"Не удалось загрузить заглушку: {settings.COVER_IMAGE_PATH}")
        
        if len(self.cover_image.shape) == 3 and self.cover_image.shape[2] == 4:
            self.has_alpha = True
        else:
            self.has_alpha = False
            logger.warning("Изображение-заглушка не имеет альфа-канала. Прозрачность может работать некорректно.")

        logger.info(f"Изображение-заглушка {settings.COVER_IMAGE_PATH} загружено.")


    def _get_destination_points(self, obb_box):
        # Эта функция слишком низкоуровневая и быстрая для логирования.
        # Оставляем ее без изменений.
        points = obb_box.xyxyxyxy[0].cpu().numpy().reshape(4, 2)
        rect = np.zeros((4, 2), dtype="float32")
        s = points.sum(axis=1)
        rect[0] = points[np.argmin(s)]
        rect[2] = points[np.argmax(s)]
        diff = np.diff(points, axis=1)
        rect[1] = points[np.argmin(diff)]
        rect[3] = points[np.argmax(diff)]
        return rect
        
    def _apply_cover_to_one_image(self, image: np.ndarray, obb_results) -> np.ndarray:
        """
        Приватный метод для наложения заглушек на одно изображение по готовым результатам детекции.
        """
        processed_image = image.copy()
        
        if obb_results is None:
            return processed_image

        num_detections = len(obb_results)
        if num_detections > 0:
            logger.debug(f"Наложение {num_detections} заглушек на изображение.")

        for box in obb_results:
            dest_points = self._get_destination_points(box)
            h, w = self.cover_image.shape[:2]
            src_points = np.array([
                [0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]
            ], dtype=np.float32)
            
            M = cv2.getPerspectiveTransform(src_points, dest_points)
            warped_cover = cv2.warpPerspective(self.cover_image, M, (processed_image.shape[1], processed_image.shape[0]))
            
            if self.has_alpha:
                mask = warped_cover[:, :, 3]
            else:
                gray_warped = cv2.cvtColor(warped_cover, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(gray_warped, 1, 255, cv2.THRESH_BINARY)
            
            mask_inv = cv2.bitwise_not(mask)
            background = cv2.bitwise_and(processed_image, processed_image, mask=mask_inv)
            
            foreground_warped = cv2.bitwise_and(warped_cover, warped_cover, mask=mask)
            if self.has_alpha:
                foreground = foreground_warped[:, :, :3]
            else:
                foreground = foreground_warped

            processed_image = cv2.add(background, foreground.astype(processed_image.dtype))
            
        return processed_image

    def cover_plate(self, image: np.ndarray) -> np.ndarray:
        """
        Одиночная обработка: Находит номера на изображении и накладывает заглушку.
        """
        logger.info("Запущена одиночная обработка изображения.")
        start_time = time.time()

        results = self.model(image, device=self.device, verbose=False)
        obb_results = results[0].obb 
        
        processed_image = self._apply_cover_to_one_image(image, obb_results)

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
        logger.info(f"Запущена пакетная обработка для {num_images} изображений с размером батча {batch_size}.")
        start_time = time.time()

        results_batch = self.model(
            images, 
            device=self.device, 
            verbose=False, 
            batch=batch_size, 
            imgsz=imgsz
        )
        
        processed_images = []
        
        for original_image, results in zip(images, results_batch):
            obb_results = results.obb
            processed_image = self._apply_cover_to_one_image(original_image, obb_results)
            processed_images.append(processed_image)
            
        end_time = time.time()
        total_time = end_time - start_time
        time_per_image = total_time / num_images if num_images > 0 else 0
        logger.info(f"Пакетная обработка {num_images} изображений завершена за {total_time:.4f} секунд ({time_per_image:.4f} сек/изображение).")

        return processed_images