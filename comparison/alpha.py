alpha_tag = 1

def alpha_fn():
    return f"alpha_fn: tag={alpha_tag}"

class Alpha:
    def __init__(self):
        self.tag = alpha_tag
    def __str__(self):
        return f"Alpha<tag={self.tag}>"
