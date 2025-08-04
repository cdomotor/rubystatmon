class StationsController < ApplicationController
  before_action :set_station, only: %i[ show edit update destroy ]

  require 'csv'

  def import
    file = params[:file]
    if file.nil?
      redirect_to stations_path, alert: "Please select a CSV file to import"
      return
    end

    CSV.foreach(file.path, headers: true) do |row|
      Station.create!(row.to_hash)
    end

    redirect_to stations_path, notice: "Stations imported successfully"
  end

  # GET /stations or /stations.json
  def index
    @stations = Station.all
  end

  # GET /stations/1 or /stations/1.json
  def show
  end

  # GET /stations/new
  def new
    @station = Station.new
  end

  # GET /stations/1/edit
  def edit
  end

  # POST /stations or /stations.json
  def create
    @station = Station.new(station_params)

    respond_to do |format|
      if @station.save
        format.html { redirect_to @station, notice: "Station was successfully created." }
        format.json { render :show, status: :created, location: @station }
      else
        format.html { render :new, status: :unprocessable_entity }
        format.json { render json: @station.errors, status: :unprocessable_entity }
      end
    end
  end

  # PATCH/PUT /stations/1 or /stations/1.json
  def update
    respond_to do |format|
      if @station.update(station_params)
        format.html { redirect_to @station, notice: "Station was successfully updated." }
        format.json { render :show, status: :ok, location: @station }
      else
        format.html { render :edit, status: :unprocessable_entity }
        format.json { render json: @station.errors, status: :unprocessable_entity }
      end
    end
  end

  # DELETE /stations/1 or /stations/1.json
  def destroy
    @station.destroy!

    respond_to do |format|
      format.html { redirect_to stations_path, status: :see_other, notice: "Station was successfully destroyed." }
      format.json { head :no_content }
    end
  end

  def ping
    @station = Station.find(params[:id])
    ip = @station.ip_address

    if Gem.win_platform?
      output = `ping -n 1 -w 1000 #{ip}`
      success = $?.exitstatus == 0
      latency = output[/Average = (\d+)ms/, 1]&.to_i
    else
      output = `ping -c 1 -W 1 #{ip}`
      success = $?.exitstatus == 0
      latency = output[/time=(\d+(?:\.\d+)?) ms/, 1]&.to_f&.round
    end

    @station.ping_results.create!(
      timestamp: Time.current,
      latency_ms: latency,   # nil if not parseable
      success: success
    )

    respond_to do |format|
      format.turbo_stream do
        render turbo_stream: turbo_stream.replace(
          "ping_result_#{@station.id}",
          partial: "stations/ping_result",
          locals: { station: @station }
        )
      end
      format.html { redirect_to @station, notice: success ? "Ping succeeded" : "Ping failed" }
      format.json { render json: { success: success, latency_ms: latency }, status: :ok }
    end
  end




  private
    # Use callbacks to share common setup or constraints between actions.
    def set_station
      @station = Station.find(params[:id])
    end

    # Only allow a list of trusted parameters through.
    def station_params
      params.require(:station).permit(:name, :ip_address, :location, :notes)
    end
end
