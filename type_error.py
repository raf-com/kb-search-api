# Test Case 5: Type Error
def add_numbers(a: int, b: int) -> int:
    return a + b

# This should cause a type error - passing string instead of int
result = add_numbers('5', '10')  # Type mismatch
print(result)

