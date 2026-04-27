import os
os.environ['YOLO_VERBOSE'] = 'False'

from ultralytics import YOLO
import torch
import numpy as np
import cv2

class Detector:
    def __init__(self, config):
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        model_settings = config.get("model_settings", {})
        self.use_main_model = model_settings.get("use_main_model", True)
        self.use_adamantite_model = model_settings.get("use_adamantite_model", False)
        
        self.main_model = None
        if self.use_main_model:
            main_model_path = "best.pt"
            if os.path.exists(main_model_path):
                self.main_model = YOLO(main_model_path, verbose=False)
                self.main_model.to(self.device)
                print(f"[MODEL] best.pt classes: {self.main_model.names}")
            else:
                self.use_main_model = False
        
        self.adamantite_model = None
        adamantite_path = "adamantite.pt"
        if self.use_adamantite_model and os.path.exists(adamantite_path):
            self.adamantite_model = YOLO(adamantite_path, verbose=False)
            self.adamantite_model.to(self.device)
        else:
            self.use_adamantite_model = False
        
        self.conf_threshold = config.get("detection_settings", {}).get("confidence_threshold", 0.75)
        
    def detect_with_vis(self, frame, window_region):
        # Read confidence threshold dynamically from config (in case user changed it in GUI)
        self.conf_threshold = self.config.get("detection_settings", {}).get("confidence_threshold", 0.75)
        # Clamp confidence between 0.01 and 1.0 to avoid invalid YOLO values
        self.conf_threshold = max(0.01, min(1.0, self.conf_threshold))
        
        all_detections = []
        
        # Run main model if enabled
        results_main = []
        if self.main_model is not None:
            results_main = self.main_model(frame, conf=self.conf_threshold, device=self.device, verbose=False)
        
        for result in results_main:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    class_id = int(box.cls[0])
                    class_name = self.main_model.names[class_id]
                    
                    if class_name == "empty_ore_rock":
                        if not self.config.get("show_empty_ore", False):
                            continue
                    elif not self.config.get("ore_checkboxes", {}).get(class_name, False):
                        # Only show selected ores
                        continue

                    if class_name == "adamantite_rock" and self.use_adamantite_model:
                        continue
                    
                    all_detections.append({
                        "box": (x1, y1, x2, y2),
                        "confidence": conf,
                        "class_id": class_id,
                        "class_name": class_name
                    })
        
        # Run adamantite model
        if self.use_adamantite_model and self.config["ore_checkboxes"].get("adamantite_rock", False):
            results_adam = self.adamantite_model(frame, conf=self.conf_threshold, device=self.device, verbose=False)
            
            for result in results_adam:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        class_id = int(box.cls[0])
                        class_name = self.adamantite_model.names[class_id]
                        
                        all_detections.append({
                            "box": (x1, y1, x2, y2),
                            "confidence": conf,
                            "class_id": class_id,
                            "class_name": class_name
                        })
        
        annotated_frame = frame.copy()

        ORE_COLORS = {
            'adamantite': (0,   0,   255),
            'mithril':    (200, 0,   200),
            'coal':       (140, 140, 140),
            'iron':       (220, 220, 220),
            'tin':        (255, 230,   0),
            'copper':     (0,  165,  255),
            'empty':      (0,  220,  220),
        }

        ORE_LABELS = {
            'adamantite_rock': 'Addy',
            'mithril_rock':    'Mith',
            'coal_rock':       'Coal',
            'iron_rock':       'Iron',
            'tin_rock':        'Tin',
            'copper_rock':     'Copper',
            'empty_ore_rock':  'Empty',
        }

        box_w = max(1, self.config.get('overlay_box_thickness', 2))
        for det in all_detections:
            x1, y1, x2, y2 = [int(v) for v in det["box"]]
            conf       = det["confidence"]
            class_name = det["class_name"]

            color = next((v for k, v in ORE_COLORS.items() if k in class_name), (0, 255, 0))

            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, box_w)

            short = ORE_LABELS.get(class_name, class_name.replace('_rock', '').title())
            label = f'{short}  {conf:.0%}'
            cv2.putText(annotated_frame, label, (x1, max(y1 - 4, 10)),
                        cv2.FONT_HERSHEY_DUPLEX, 0.5, color, 1, cv2.LINE_AA)

        return all_detections, annotated_frame