import numpy as np

a = np.array(list(range(100)))

def hello():
    x = 0
    for i in range(0, 10):
        x += i
    return x


r = hello()
a[5] = r
print(sum(a))
