# src/processor.py
import cv2
import numpy as np
from ultralytics import YOLO

class NumberPlateCoverer:
    """
    Класс для детекции автомобильных номеров с помощью YOLOv8-OBB
    и наложения на них кастомного изображения.
    """
    def __init__(self, model_path: str, cover_image_path: str, device: str = 'cpu'):
        """
        Инициализирует обработчик.
        """
        self.model = YOLO(model_path)
        self.device = device
        self.model.to(self.device)
        print(f"Модель {model_path} загружена на устройство {self.device}.")

        self.cover_image = cv2.imread(cover_image_path, cv2.IMREAD_UNCHANGED)
        if self.cover_image is None:
            raise FileNotFoundError(f"Не удалось загрузить изображение-заглушку: {cover_image_path}")
        
        # Проверяем наличие альфа-канала
        has_alpha = self.cover_image.shape[2] == 4
        if not has_alpha:
            print("Предупреждение: Изображение-заглушка не имеет альфа-канала. Прозрачность может работать некорректно.")

        print(f"Изображение-заглушка {cover_image_path} загружено.")

    def _get_destination_points(self, obb_box):
        """
        Извлекает и упорядочивает 4 угловые точки из результата OBB.
        Эта версия использует математически надежный метод, чтобы избежать ошибок ориентации.
        """
        points = obb_box.xyxyxyxy[0].cpu().numpy().reshape(4, 2)
        
        # Создаем пустой массив для отсортированных точек
        # Порядок: 0:TL, 1:TR, 2:BR, 3:BL (по часовой стрелке)
        rect = np.zeros((4, 2), dtype="float32")
        
        # Верхний левый угол будет иметь наименьшую сумму, а
        # нижний правый - наибольшую сумму
        s = points.sum(axis=1)
        rect[0] = points[np.argmin(s)] # Top-Left
        rect[2] = points[np.argmax(s)] # Bottom-Right
        
        # Теперь найдем верхний правый и нижний левый углы,
        # вычисляя разницу между точками
        diff = np.diff(points, axis=1)
        rect[1] = points[np.argmin(diff)] # Top-Right
        rect[3] = points[np.argmax(diff)] # Bottom-Left
        
        # Возвращаем отсортированные координаты
        return rect

    def cover_plate(self, image: np.ndarray, debug: bool = False) -> np.ndarray:
        """
        Находит номера на изображении и накладывает на них заглушку.

        :param image: Изображение в формате NumPy array (BGR).
        :param debug: Если True, будет рисовать отладочную информацию (точки и их порядок).
        :return: Изображение с наложенной заглушкой.
        """
        results = self.model(image, device=self.device, verbose=False)
        processed_image = image.copy()

        for res in results:
            if res.obb is None:
                continue
            
            for box in res.obb:
                # 1. Получаем 4 точки назначения
                dest_points = self._get_destination_points(box)

                # --- ОТЛАДОЧНЫЙ БЛОК ---
                if debug:
                    for i, point in enumerate(dest_points):
                        px, py = int(point[0]), int(point[1])
                        cv2.circle(processed_image, (px, py), 10, (0, 255, 255), -1)
                        cv2.putText(processed_image, str(i), (px + 5, py + 5), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                    continue
                # --- КОНЕЦ ОТЛАДОЧНОГО БЛОКА ---

                # 2. Определяем 4 исходные точки в порядке ПО ЧАСОВОЙ СТРЕЛКЕ
                h, w = self.cover_image.shape[:2]
                src_points = np.array([
                    [0, 0],         # 0: Верх-лево (TL)
                    [w - 1, 0],     # 1: Верх-право (TR)
                    [w - 1, h - 1], # 2: Низ-право (BR)
                    [0, h - 1]      # 3: Низ-лево (BL)
                ], dtype=np.float32)
                
                # 3. Вычисляем матрицу преобразования
                M = cv2.getPerspectiveTransform(src_points, dest_points)

                # 4. "Искажаем" нашу заглушку
                warped_cover = cv2.warpPerspective(self.cover_image, M, (processed_image.shape[1], processed_image.shape[0]))
                
                # 5. Создаем маску для наложения
                has_alpha = warped_cover.shape[2] == 4
                if has_alpha:
                    mask = warped_cover[:, :, 3]
                else:
                    gray_warped = cv2.cvtColor(warped_cover, cv2.COLOR_BGR2GRAY)
                    _, mask = cv2.threshold(gray_warped, 1, 255, cv2.THRESH_BINARY)
                
                mask_inv = cv2.bitwise_not(mask)

                # 6. Накладываем изображение
                background = cv2.bitwise_and(processed_image, processed_image, mask=mask_inv)
                
                foreground = cv2.bitwise_and(warped_cover, warped_cover, mask=mask)
                if has_alpha:
                    foreground = foreground[:, :, :3]

                processed_image = cv2.add(background, foreground.astype(processed_image.dtype))
                
        return processed_image