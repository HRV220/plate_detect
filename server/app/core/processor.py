# server/app/core/processor.py

import gc
import logging
import time
from typing import List

import cv2
import numpy as np
from ultralytics import YOLO
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


async def create_number_plate_coverer() -> "NumberPlateCoverer":
    """
    Асинхронная фабрика для создания и инициализации NumberPlateCoverer.
    Выносит все блокирующие операции (загрузка модели и изображения) в тредпул,
    не замораживая event loop во время старта приложения.
    """
    logger.info("Асинхронная инициализация NumberPlateCoverer...")

    # Блокирующую загрузку изображения-заглушки выносим в отдельный поток
    cover_image = await run_in_threadpool(
        cv2.imread, settings.COVER_IMAGE_PATH, cv2.IMREAD_UNCHANGED
    )
    
    if cover_image is None:
        raise FileNotFoundError(f"Файл не найден или имеет неверный формат: {settings.COVER_IMAGE_PATH}")
    
    # Инициализация модели также может быть долгой, поэтому ее тоже можно обернуть,
    # но для ясности оставим так. Главное, что вся функция асинхронна.
    model = YOLO(settings.MODEL_PATH)
    
    instance = NumberPlateCoverer(model, cover_image)
    logger.info("NumberPlateCoverer успешно инициализирован.")
    return instance


class NumberPlateCoverer:
    """
    Класс для детекции и сокрытия номеров.
    Инициализируется через асинхронную фабрику `create_number_plate_coverer`.
    Его методы являются синхронными и предназначены для вызова в тредпуле.
    """
    def __init__(self, model: YOLO, cover_image: np.ndarray):
        # __init__ теперь полностью синхронный, быстрый и не выполняет I/O.
        # Он только принимает готовые объекты.
        self.device = settings.PROCESSING_DEVICE
        self.model = model
        self.model.to(self.device)
        logger.info(f"Модель YOLO перенесена на устройство: {self.device}.")

        self.cover_image = cover_image
        self.has_alpha = len(self.cover_image.shape) == 3 and self.cover_image.shape[2] == 4
        if not self.has_alpha:
            logger.warning("Изображение-заглушка не имеет альфа-канала.")

    def _get_destination_points(self, obb_box) -> np.ndarray:
        # Этот метод остается без изменений.
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
        # Этот метод остается без изменений.
        if not obb_results:
            return image

        processed_image = image.copy()
        for box in obb_results:
            dest_points = self._get_destination_points(box)
            h, w = self.cover_image.shape[:2]
            src_points = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
            M = cv2.getPerspectiveTransform(src_points, dest_points)
            warped_cover = cv2.warpPerspective(
                self.cover_image, M, (processed_image.shape[1], processed_image.shape[0])
            )
            if self.has_alpha:
                mask = warped_cover[:, :, 3]
            else:
                gray_warped = cv2.cvtColor(warped_cover, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(gray_warped, 1, 255, cv2.THRESH_BINARY)
            mask_inv = cv2.bitwise_not(mask)
            background = cv2.bitwise_and(processed_image, processed_image, mask=mask_inv)
            foreground_bgr = warped_cover[:, :, :3] if self.has_alpha else warped_cover
            foreground = cv2.bitwise_and(foreground_bgr, foreground_bgr, mask=mask)
            processed_image = cv2.add(background, foreground.astype(processed_image.dtype))
            
        return processed_image

    def cover_plates_batch(self, images: List[np.ndarray], batch_size: int = 16, imgsz: int = 640) -> List[np.ndarray]:
        """
        Пакетная обработка. Этот метод СИНХРОННЫЙ и БЛОКИРУЮЩИЙ.
        Он содержит тяжелые вычисления и должен вызываться через run_in_threadpool.
        """
        if not images:
            return []

        num_images = len(images)
        logger.debug(f"Начало синхронной пакетной обработки для {num_images} изображений.")
        start_time = time.time()
        
        processed_images = []
        results_batch = None

        try:
            results_batch = self.model(
                images, device=self.device, verbose=False, batch=batch_size, imgsz=imgsz
            )
            
            for original_image, results in zip(images, results_batch):
                obb_results = results.obb
                processed_image = self._apply_cover_to_one_image(original_image, obb_results)
                processed_images.append(processed_image)
        finally:
            del results_batch
            gc.collect()
            logger.debug("Ресурсы после пакетной обработки освобождены сборщиком мусора.")

        end_time = time.time()
        total_time = end_time - start_time
        logger.info(
            f"Синхронная пакетная обработка завершена за {total_time:.4f} сек."
        )

        return processed_images