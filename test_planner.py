import planner
import markdown_io

trip_input = markdown_io.read_trip_input()
print("Starting generation...")
plan = planner.generate_plan(trip_input)
print("\n--- GENERATED PLAN ---\n")
print(plan)
