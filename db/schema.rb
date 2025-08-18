# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[7.1].define(version: 2025_08_16_060000) do
  create_table "ping_results", force: :cascade do |t|
    t.integer "station_id", null: false
    t.integer "latency_ms"
    t.datetime "timestamp"
    t.boolean "success"
    t.integer "failure_count"
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.index ["station_id"], name: "index_ping_results_on_station_id"
  end

  create_table "readings", force: :cascade do |t|
    t.integer "station_id", null: false
    t.string "parameter", null: false
    t.float "value"
    t.datetime "taken_at", null: false
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.index ["station_id", "parameter", "taken_at"], name: "index_readings_on_station_id_and_parameter_and_taken_at"
    t.index ["station_id"], name: "index_readings_on_station_id"
  end

  create_table "stations", force: :cascade do |t|
    t.string "name"
    t.string "ip_address"
    t.string "location"
    t.text "notes"
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.text "configured_parameters", default: "[]", null: false
    t.boolean "active", default: true, null: false
    t.index ["active"], name: "index_stations_on_active"
  end

  add_foreign_key "ping_results", "stations"
  add_foreign_key "readings", "stations"
end
