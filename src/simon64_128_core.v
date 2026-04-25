`default_nettype none

module simon64_128_core (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       decrypt,
    input  wire       key_byte_valid,
    input  wire [7:0] key_byte,
    input  wire       block_byte_valid,
    input  wire [7:0] block_byte,
    output reg        busy,
    output reg        done,
    output wire [63:0] block_out
);
  localparam [1:0] ST_IDLE   = 2'd0;
  localparam [1:0] ST_RUN    = 2'd1;
  localparam [1:0] ST_WARMUP = 2'd2;

  localparam [31:0] C_CONST = 32'hffff_fffc;

  reg [1:0]   phase;

  reg         k_at_final;

  reg [31:0]  x_reg;
  reg [31:0]  y_reg;

  reg [127:0] k_window;

  reg [6:0]   z_lfsr;

  reg [5:0]   ctr_round;
  reg [4:0]   ctr_bit;
  reg         op_decrypt;

  // Key window words
  wire [31:0] kw0 = k_window[31:0];
  wire [31:0] kw1 = k_window[63:32];
  wire [31:0] kw2 = k_window[95:64];
  wire [31:0] kw3 = k_window[127:96];

  wire        z_bit      = z_lfsr[0];
  wire        z_bit_inv  = z_lfsr[6] ^ z_lfsr[3] ^ z_lfsr[0];
  wire [6:0]  z_lfsr_fwd = {z_lfsr[4]^z_lfsr[1]^z_lfsr[0], z_lfsr[6:1]};
  wire [6:0]  z_lfsr_bwd = {z_lfsr[5:0], z_lfsr[6]^z_lfsr[3]^z_lfsr[0]};

  wire         ks_forward = (phase == ST_WARMUP) ? op_decrypt : !op_decrypt;
  wire [31:0]  ks_rot_src = ks_forward ? kw3 : kw2;
  wire [31:0]  ks_xor_src = ks_forward ? kw1 : kw0;
  wire [31:0]  ks_edge    = ks_forward ? kw0 : kw3;
  wire         ks_z_bit   = ks_forward ? z_bit : z_bit_inv;
  wire [31:0]  ks_s3      = {ks_rot_src[2:0], ks_rot_src[31:3]};
  wire [31:0]  ks_mix0    = ks_s3 ^ ks_xor_src;
  wire [31:0]  ks_s1      = {ks_mix0[0], ks_mix0[31:1]};
  wire [31:0]  ks_word    = C_CONST ^ ks_z_bit ^ ks_edge ^ ks_mix0 ^ ks_s1;
  wire [127:0] k_window_step = ks_forward ? {ks_word, k_window[127:32]} : {k_window[95:0], ks_word};

  wire        x_src_bit   = op_decrypt ? x_reg[0]  : y_reg[0];
  wire        f_src_bit_0 = op_decrypt ? y_reg[31] : x_reg[31];
  wire        f_src_bit_1 = op_decrypt ? y_reg[24] : x_reg[24];
  wire        f_src_bit_2 = op_decrypt ? y_reg[30] : x_reg[30];
  wire        rk_bit      = kw0[ctr_bit];
  wire        f_bit       = (f_src_bit_0 & f_src_bit_1) ^ f_src_bit_2;
  wire        run_new_bit = x_src_bit ^ f_bit ^ rk_bit;
  wire [31:0] x_rot       = {x_reg[0], x_reg[31:1]};
  wire [31:0] y_rot       = {y_reg[0], y_reg[31:1]};
  wire [31:0] x_new_shift = {run_new_bit, x_reg[31:1]};
  wire [31:0] y_new_shift = {run_new_bit, y_reg[31:1]};

  assign block_out = {x_reg, y_reg};

  always @(posedge clk) begin
    if (!rst_n) begin
      phase      <= ST_IDLE;
      busy       <= 1'b0;
      done       <= 1'b0;
      k_at_final <= 1'b0;
      ctr_round  <= 6'd0;
      ctr_bit    <= 5'd0;
      op_decrypt <= 1'b0;
      z_lfsr     <= 7'h5b;   // initial state for z_idx=0
    end else begin
      done <= 1'b0;

      if (!busy) begin
        if (key_byte_valid) begin
          k_window   <= {k_window[119:0], key_byte};
          k_at_final <= 1'b0;
          z_lfsr     <= 7'h5b;
        end
        if (block_byte_valid) begin
          x_reg <= {x_reg[23:0], y_reg[31:24]};
          y_reg <= {y_reg[23:0], block_byte};
        end
      end

      case (phase)
        ST_IDLE: begin
          if (start) begin
            busy       <= 1'b1;
            ctr_round  <= 6'd0;
            ctr_bit    <= 5'd0;
            op_decrypt <= decrypt;

            if (decrypt != k_at_final) begin
              phase <= ST_WARMUP;
            end else begin
              phase <= ST_RUN;
            end
          end
        end

        ST_WARMUP: begin
          k_window <= k_window_step;
          z_lfsr   <= ks_forward ? z_lfsr_fwd : z_lfsr_bwd;

          if (ctr_round == 6'd42) begin
            k_at_final <= op_decrypt;
            ctr_round  <= 6'd0;
            phase      <= ST_RUN;
          end else begin
            ctr_round <= ctr_round + 6'd1;
          end
        end

        ST_RUN: begin
          if (op_decrypt) begin
            x_reg <= x_new_shift;
            y_reg <= y_rot;
          end else begin
            x_reg <= x_rot;
            y_reg <= y_new_shift;
          end
          ctr_bit <= ctr_bit + 5'd1;

          if (ctr_bit == 5'd31) begin
            ctr_bit <= 5'd0;

            if (ctr_round == 6'd43) begin
              // Last round complete.
              if (op_decrypt) begin
                x_reg <= y_rot;
                y_reg <= x_new_shift;
              end else begin
                x_reg <= y_new_shift;
                y_reg <= x_rot;
              end
              busy       <= 1'b0;
              done       <= 1'b1;
              k_at_final <= ~op_decrypt;
              phase      <= ST_IDLE;
            end else begin
              ctr_round <= ctr_round + 6'd1;

              if (op_decrypt) begin
                x_reg    <= y_rot;
                y_reg    <= x_new_shift;
                k_window <= k_window_step;
                z_lfsr   <= z_lfsr_bwd;
              end else begin
                x_reg    <= y_new_shift;
                y_reg    <= x_rot;
                k_window <= k_window_step;
                z_lfsr   <= z_lfsr_fwd;
              end
            end
          end
        end

        default: begin
          phase <= ST_IDLE;
        end
      endcase
    end
  end

endmodule
