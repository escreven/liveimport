gamma_tag = 1
gamma_second = gamma_tag

def gamma_fn():
    return f"gamma_fn: tag={gamma_tag}; second={gamma_second}"

class Gamma:
    def __init__(self):
        self.tag = gamma_tag
        self.second = gamma_second
    def __str__(self):
        return f"Gamma<tag={self.tag}; second={self.second}>"
