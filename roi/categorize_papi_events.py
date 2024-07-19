import os
import json
import re
import shutil
import subprocess

from pathlib import Path

cc = "gcc"

roi_dir = Path(__file__).parent
roi_inc_dir = roi_dir / "include"
roi_lib_dir = roi_dir / "lib"

papi_dir = roi_dir / "papi/install"
papi_inc_dir = papi_dir / "include"
papi_lib_dir = papi_dir / "lib"

papi_bin_dir = papi_dir / "bin"
papi_avail = papi_bin_dir / "papi_avail"


def _find_json_files(dir: Path) -> list:
    return [item for item in os.listdir(dir) if item.endswith(".json")]


def compile_test_program() -> Path:
    test_program = """
#include <stdio.h>
#include "roi.h"


int main() {
    int i;
    annotate_init_();
    region_begin_("main");
    for (i = 0; i < 64; i++){
        printf("Hello, World!\\n");
    }
    region_end_("main");
    return 0;
}

"""
    c_file_path = Path("/tmp/papi_events_test_program.c")
    binary_file_path = Path("/tmp/papi_events_test_program")
    with open(c_file_path, "w") as test_program_file:
        test_program_file.write(test_program)

    compiler_flags = (
        f"-I{roi_inc_dir} -I{papi_inc_dir} -L{roi_lib_dir} "
        f"-L{papi_lib_dir} -lroi.papi -lpapi -lpthread"
    )

    compile_cmd = f"{cc} {c_file_path} -o {binary_file_path} {compiler_flags}"
    _ = subprocess.run(
        [compile_cmd],
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return binary_file_path


def get_papi_event_list(skip_derived=False) -> list:
    num_counters = -1
    event_list = []
    max_counter_pattern = r"^\s*Number\s+Hardware\s+Counters\s*:\s*\d+\s*$"
    header_pattern = r"^\s*Name\s+Code\s+Deriv\s+Description\s+\(Note\)\s*$"
    footer_pattern = r"^\s*-+\s*$"

    cmd = [str(papi_avail), "-a"]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    captured_stdout = result.stdout
    lines = captured_stdout.split("\n")
    seen_header = False
    seen_footer = False
    for line in lines:
        if re.match(max_counter_pattern, line):
            num_counters = int(line.split()[-1])
        if re.match(header_pattern, line):
            seen_header = True
            continue
        if re.match(footer_pattern, line) and seen_header:
            seen_footer = True
            continue
        if seen_header and not seen_footer:
            event, _, derived = line.split()[:3]
            if skip_derived and derived == "Yes":
                continue
            event_list.append(event)
    return num_counters, event_list


def find_forbidden_pairs(event_list: list, test_binary: Path):
    forbidden_pairs = {}
    for event0 in event_list:
        for event1 in event_list:
            if event0 == event1:
                continue
            ld_add_papi = f"LD_LIBRARY_PATH={papi_lib_dir}:$LD_LIBRARY_PATH"
            papi_events = f"PAPI_EVENTS='{event0}','{event1}'"
            papi_output_dir = Path(f"{roi_dir}/papi_output")
            try:
                shutil.rmtree(papi_output_dir)
            except FileNotFoundError:
                print(f"Directory {papi_output_dir} does not exist.")
            except Exception as e:
                raise e
            papi_outdir = f"PAPI_OUTPUT_DIRECTORY={papi_output_dir}"
            run_test_binary = f"{test_binary}"
            cmd = (
                f"{ld_add_papi} {papi_events} {papi_outdir} {run_test_binary}"
            )
            _ = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            json_files = _find_json_files(papi_output_dir / "papi_hl_output")
            assert len(json_files) == 1
            papi_out = json_files[0]
            with open(
                papi_output_dir / "papi_hl_output" / papi_out
            ) as papi_out_file:
                papi_out_data = json.load(papi_out_file)
            to_search = papi_out_data["threads"]["0"]["regions"]["0"]
            if not (event0 in to_search and event1 in to_search):
                if event0 not in forbidden_pairs:
                    forbidden_pairs[event0] = []
                if event1 not in forbidden_pairs:
                    forbidden_pairs[event1] = []
                forbidden_pairs[event0].append(event1)
                forbidden_pairs[event1].append(event0)

    return forbidden_pairs


def test_events(event_list: list, test_binary: Path):
    ret = True
    ld_add_papi = f"LD_LIBRARY_PATH={papi_lib_dir}:$LD_LIBRARY_PATH"
    events = [f"'{event}'" for event in event_list]
    papi_events = f"PAPI_EVENTS={','.join(events)}"
    papi_output_dir = Path(f"{roi_dir}/papi_output")
    try:
        shutil.rmtree(papi_output_dir)
    except FileNotFoundError:
        print(f"Directory {papi_output_dir} does not exist.")
    except Exception as e:
        raise e
    papi_outdir = f"PAPI_OUTPUT_DIRECTORY={papi_output_dir}"
    run_test_binary = f"{test_binary}"
    cmd = f"{ld_add_papi} {papi_events} {papi_outdir} {run_test_binary}"
    _ = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    json_files = _find_json_files(papi_output_dir / "papi_hl_output")
    assert len(json_files) == 1
    papi_out = json_files[0]
    with open(papi_output_dir / "papi_hl_output" / papi_out) as papi_out_file:
        papi_out_data = json.load(papi_out_file)
    to_search = papi_out_data["threads"]["0"]["regions"]["0"]
    for event in event_list:
        ret &= event in to_search
    return ret


def partition_papi_events(
    event_list: list, max_partition_size: int, test_binary: Path
):
    def _all_subsets(in_set: list, max_length: int, current_set: list):
        if len(current_set) == max_length:
            return [current_set]
        if len(in_set) + len(current_set) < max_length:
            return []

        current_item = in_set[0]
        rest = in_set[1:]
        return _all_subsets(rest, max_length, current_set) + _all_subsets(
            rest, max_length, current_set + [current_item]
        )

    remaining_events = event_list.copy()

    partitions = []
    while len(remaining_events) > 0:
        subsets = _all_subsets(
            remaining_events,
            min(len(remaining_events), max_partition_size),
            [],
        )
        for subset in subsets:
            if test_events(subset, test_binary):
                select = subset
                break
        partitions.append(select)
        new_remaining_events = []
        for event in remaining_events:
            if not event in select:
                new_remaining_events.append(event)
        if len(new_remaining_events) == len(remaining_events):
            print(f"Could not find a partition for {remaining_events}.")
            break
        remaining_events = new_remaining_events

    return partitions


if __name__ == "__main__":
    test_binary = compile_test_program()
    num_counters, event_list = get_papi_event_list(skip_derived=True)
    partitions = partition_papi_events(event_list, num_counters, test_binary)
    print(partitions)
