import random

def shuffled(arr):
    result = arr[:]
    n = len(result)
    for i in range(n - 1, 0, -1):
        j = random.randint(0, i)
        result[i], result[j] = result[j], result[i]
    return result

if __name__ == "__main__":
    # Example usage
    original = [1, 2, 3, 4, 5]
    shuffled_list = shuffled(original)
    print("Original:", original)
    print("Shuffled:", shuffled_list)