delta_tag = 1

def delta_fn():
    return f"delta_fn: tag={delta_tag}"

class Delta:
    def __init__(self):
        self.tag = delta_tag
    def __str__(self):
        return f"Delta<tag={self.tag}>"


common_int = 99
common_str = "Common string in delta.py"

def common_fn():
    return "Common function in delta.py"

def Common():
    def __init__(self):
        pass
    def __str__(self):
        return "Common class in delta.py"
