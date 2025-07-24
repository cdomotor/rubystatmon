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
