# src/processor.py
import cv2
import numpy as np
from ultralytics import YOLO
from typing import List

class NumberPlateCoverer:
    """
    Класс для детекции автомобильных номеров с помощью YOLOv8-OBB
    и наложения на них кастомного изображения.
    Поддерживает одиночную и пакетную обработку.
    """
    def __init__(self, model_path: str, cover_image_path: str, device: str = 'cpu'):
        self.model = YOLO(model_path)
        self.device = device
        self.model.to(self.device)
        print(f"Модель {model_path} загружена на устройство {self.device}.")

        self.cover_image = cv2.imread(cover_image_path, cv2.IMREAD_UNCHANGED)
        if self.cover_image is None:
            raise FileNotFoundError(f"Не удалось загрузить изображение-заглушку: {cover_image_path}")
        
        self.has_alpha = self.cover_image.shape[2] == 4
        if not self.has_alpha:
            print("Предупреждение: Изображение-заглушка не имеет альфа-канала. Прозрачность может работать некорректно.")

        print(f"Изображение-заглушка {cover_image_path} загружено.")

    def _get_destination_points(self, obb_box):
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
        # Выполняем детекцию для одного изображения
        results = self.model(image, device=self.device, verbose=False)
        # res.obb может быть None, если ничего не найдено
        obb_results = results[0].obb 
        
        return self._apply_cover_to_one_image(image, obb_results)
        
    def cover_plates_batch(self, images: List[np.ndarray], batch_size: int = 16, imgsz: int = 640) -> List[np.ndarray]:
        """
        Пакетная обработка: Находит номера на списке изображений и накладывает заглушки.
        
        :param images: Список изображений в формате NumPy array (BGR).
        :param batch_size: Размер батча для обработки моделью.
        :param imgsz: Размер, до которого будут изменены изображения для детекции.
        :return: Список обработанных изображений.
        """
        if not images:
            return []

        # 1. Выполняем детекцию для всего списка изображений за один вызов
        # Модель сама разделит их на батчи нужного размера.
        results_batch = self.model(
            images, 
            device=self.device, 
            verbose=False, 
            batch=batch_size, 
            imgsz=imgsz
        )
        
        processed_images = []
        
        # 2. Итерируемся по оригинальным изображениям и их результатам
        for original_image, results in zip(images, results_batch):
            # res.obb может быть None, если ничего не найдено на конкретном изображении
            obb_results = results.obb
            
            # 3. Применяем логику наложения для каждого изображения
            processed_image = self._apply_cover_to_one_image(original_image, obb_results)
            processed_images.append(processed_image)
            
        return processed_images