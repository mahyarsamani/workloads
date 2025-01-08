from math import comb
from random import shuffle

from pypapi import events, EventSet
from pypapi.library import init as papi_init


# Function to check if a set of events can be measured together
def can_measure_together(event_list):
    # Initialize pypapi library
    papi_init()

    # Create an event set
    event_set = EventSet()

    try:
        # Add events to the event set
        for event in event_list:
            event_set.add_named(event)

        # Check if the event set can be started
        event_set.start()
        event_set.stop()

        # If no exception is raised, the events can be measured together
        return True
    except pypapi.pypapiError:
        # If an exception is raised, the events cannot be measured together
        return False
    finally:
        # Cleanup
        event_set.cleanup()


def partition_pypapi_events(
    event_list: list,
    og_max_partition_size: int,
    window_size: int,
    necessary_shuffle_limit: int = 3,
):
    def _all_subsets(in_set: list, max_length: int, current_set: list):
        if len(current_set) == max_length:
            return [current_set]
        if len(in_set) + len(current_set) < max_length:
            return []

        current_item = in_set[0]
        return _all_subsets(
            in_set[1:], max_length, current_set
        ) + _all_subsets(in_set[1:], max_length, current_set + [current_item])

    partitions = []
    necessary_shuffles = 0
    remaining_events = event_list.copy()
    max_partition_size = og_max_partition_size
    while len(remaining_events) > 0:
        window = remaining_events[:window_size]
        subsets = _all_subsets(
            window,
            min(len(remaining_events), max_partition_size),
            [],
        )
        print(f"There are a total of {len(subsets)} subsets.")
        select = []
        for subset in subsets:
            if can_measure_together(subset):
                select = subset
                partitions.append(select)
                print(f"Found suitable subset: {select}")
                if (
                    max_partition_size < og_max_partition_size
                    and necessary_shuffles == 0
                ):
                    max_partition_size = og_max_partition_size
                break
        new_remaining_events = [
            event for event in remaining_events if event not in select
        ]
        if len(new_remaining_events) == len(remaining_events):
            necessary_shuffles += 1
            if necessary_shuffles > necessary_shuffle_limit:
                print(
                    f"Hit necessary shuffle limit: {necessary_shuffle_limit}"
                )
                necessary_shuffles = 0
                max_partition_size -= 1
                continue
        if (
            len(new_remaining_events) == len(remaining_events)
            and max_partition_size == 0
        ):
            print(
                f"Could not find a partition for {remaining_events} with "
                f"max_partition_size={max_partition_size}."
            )
            break
        remaining_events = new_remaining_events
        shuffle(remaining_events)

    return partitions


def good_window_size(num_counters):
    upper_bound = 50_000
    window_size = num_counters + 1
    combinations = window_size
    while combinations < upper_bound:
        window_size += 1
        combinations = comb(window_size, num_counters)

    return window_size - 1


if __name__ == "__main__":
    print(events)
    # all_events = ???
    # num_counters = ???
    # # Partition the events
    # partitions = partition_pypapi_events(all_events, num_counters)

    # # Print the partitions
    # for i, partition in enumerate(partitions):
    #     print(f"Partition {i}: {partition}")
