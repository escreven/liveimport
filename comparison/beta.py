from alpha import alpha_tag, alpha_fn, Alpha

beta_tag = 1

def beta_fn():
    return (f"beta_fn: tag={beta_tag}"
            f", alpha_tag={alpha_tag}"
            f"; calls {alpha_fn()}")

class Beta:
    def __init__(self):
        self.tag = beta_tag
        self.alpha_tag = alpha_tag
    def __str__(self):
        return (f"Beta<tag={self.tag}"
                f", alpha_tag={self.alpha_tag}>"
                f"; constructs {Alpha()}")
