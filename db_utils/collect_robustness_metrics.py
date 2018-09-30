from db_utils.robustness_records import per_run_table, summary_table, Record,\
    reg_vs_not_reg, best_agreement

"""
RECORDS = [
    Record(0, "20180921-101852", 10),
    Record(1, "20180921-123619", 8),
    Record(2, "20180921-123639", 7),
    Record(3, "20180921-144511", 5),
    Record(4, "20180921-163338", 10),
    Record(5, "20180921-165806", 9),
    Record(6, "20180921-185237", 9),
    Record(7, "20180921-203608", 9),
    Record(8, "20180921-212036", 7),
    Record(9, "20180921-230207", 5),
]
"""

RECORDS = [
    Record(0, "20180921-101902", 7),
    Record(1, "20180921-123629", 5),
    Record(2, "20180921-143357", 6),
    Record(3, "20180921-144521", 7),
    Record(4, "20180921-165553", 7),
    Record(5, "20180921-183623", 5),
    Record(6, "20180921-190751", 7),
    Record(7, "20180921-210322", 4),
    Record(8, "20180921-223453", 11),
    Record(9, "20180921-233022", 7),
]

"""
RECORDS = [
    Record(0, "20180930-084902", 10),
    Record(1, "20180929-200012", 7),
    Record(2, "20180929-204042", 10),
    Record(3, "20180929-222914", 4),
    Record(4, "20180930-003747", 7),
    Record(5, "20180930-010815", 10),
    Record(6, "20180930-030448", 9),
    Record(7, "20180930-035417", 6),
    Record(8, "20180930-052148", 4),
    Record(9, "20180930-072921", 6),
]
"""

if __name__ == "__main__":
    per_run_table(RECORDS)
    summary_table(RECORDS)
    reg_vs_not_reg(RECORDS)
    best_agreement(RECORDS)
