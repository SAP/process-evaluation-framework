
def index_list(lst):
    """
    Takes a list and adds an index for every item in the list using Counter.
    Example: ["a", "b", "c", "c", "d", "b"] -> ["a1", "b1", "c1", "c2", "d1", "b2"]
    """
    count = {}
    indexed = []
    for item in lst:
        count[item] = count.get(item, 0) + 1
        indexed.append(f"{item}{count[item]}")
    return indexed


def dice_list(list1, list2):
    """Dice similarity is a common similarity metrics for two sets. Defining Dice Similarity function for two lists"""
    set1, set2 = set(list1), set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1) + len(set2)
    if union == 0:
        return 1, 0
    dice = float(2 * intersection) / union
    weight = (
        (2 * len(set1) * len(set2)) / (len(set1) + len(set2)) if (len(set1) + len(set2)) != 0 else 0
    )
    return dice, weight  # len(set1) + len(set2)


def jaccard_list(list1, list2):
    """Jaccard similarity is a common similarity metrics for two sets. Defining Jaccard Similarity function for two lists"""
    set1, set2 = set(list1), set(list2)
    intersection = len(set1.intersection(set2))
    union = (len(set1) + len(set2)) - intersection
    if union == 0:
        return 1, 0
    jaccard = float(intersection) / union
    weight = (
        (2 * len(set1) * len(set2)) / (len(set1) + len(set2)) if (len(set1) + len(set2)) != 0 else 0
    )

    return jaccard, weight  # len(set1) + len(set2)


def overlap_list(list1, list2):
    """Overlap coefficient (Szymkiewicz–Simpson) for two lists. https://en.wikipedia.org/wiki/Overlap_coefficient
    """
    set1, set2 = set(list1), set(list2)
    min_size = min(len(set1), len(set2))
    if min_size == 0:
        return (1, 0) if len(set1) == len(set2) else (0, 0)
    intersection = len(set1.intersection(set2))
    overlap = float(intersection) / min_size
    weight = (
        (2 * len(set1) * len(set2)) / (len(set1) + len(set2)) if (len(set1) + len(set2)) != 0 else 0
    )
    return overlap, weight


def scores(list_1, list_2, score_type="precision"):
    """list_1 is the ground truth, list_2 is the generated list"""
    # Convert lists to sets
    set1, set2 = set(list_1), set(list_2)

    # Compute the intersection of the sets
    intersection = set1.intersection(set2)
    # Calculate precision
    precision = len(intersection) / len(set2) if set2 else 0

    # Calculate recall
    recall = len(intersection) / len(set1) if set1 else 0

    weight = (
        (2 * len(set1) * len(set2)) / (len(set1) + len(set2)) if (len(set1) + len(set2)) != 0 else 0
    )
    # Calculate the F1 score
    if precision + recall == 0:
        f1 = 0  # To handle the case when both precision and recall are zero
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    if score_type == "precision":
        return precision, weight  # len(set1) + len(set2)
    elif score_type == "recall":
        return recall, weight  # len(set1) + len(set2)
    elif score_type == "f1":
        return f1, weight  # len(set1) + len(set2)
    else:
        raise ValueError("Invalid score type. Use 'precision', 'recall', or 'f1'.")







