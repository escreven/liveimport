epsilon_tag = 1

def epsilon_fn():
    return f"epsilon_fn: tag={epsilon_tag}"

class Epsilon:
    def __init__(self):
        self.tag = epsilon_tag
        #self.another = 42
    def __str__(self):
        result = f"Epsilon<tag={self.tag}"
        #result += "; CHANGED"
        #result += f"; another={self.another}"
        result += ">"
        return result
