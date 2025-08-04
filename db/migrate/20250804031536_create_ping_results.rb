class CreatePingResults < ActiveRecord::Migration[7.1]
  def change
    create_table :ping_results do |t|
      t.references :station, null: false, foreign_key: true
      t.integer :latency_ms
      t.datetime :timestamp
      t.boolean :success
      t.integer :failure_count

      t.timestamps
    end
  end
end
