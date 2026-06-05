class SlopeAnalyzer:
    def __init__(self, window: int = 20, threshold: float = 1.0):
        self.window = window
        self.threshold = threshold

    def compute(self, samples: list[tuple[int, dict[str, int]]]) -> dict[str, float]:
        """
        samples: [(arduino_ms, {sensor_name: value}), ...]
        Devuelve pendiente en unidades/segundo para cada sensor.
        """
        if len(samples) < 2:
            return {}

        sensor_names = samples[0][1].keys()
        slopes: dict[str, float] = {}

        for name in sensor_names:
            points = [(ms, vals[name]) for ms, vals in samples if name in vals]
            if len(points) < 2:
                slopes[name] = float("inf")
                continue

            n = len(points)
            sum_x = sum(x for x, _ in points)
            sum_y = sum(y for _, y in points)
            sum_xy = sum(x * y for x, y in points)
            sum_x2 = sum(x * x for x, _ in points)
            denom = n * sum_x2 - sum_x**2

            if denom == 0:
                slopes[name] = 0.0
            else:
                # arduino_ms está en milisegundos → convertir a por segundo
                slopes[name] = (n * sum_xy - sum_x * sum_y) / denom * 1000

        return slopes

    def all_stable(self, samples: list[tuple[int, dict[str, int]]]) -> bool:
        slopes = self.compute(samples)
        if not slopes:
            return False
        return all(abs(s) < self.threshold for s in slopes.values())
